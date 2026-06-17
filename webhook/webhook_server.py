"""
GitHub push webhook listener.

Triggered when trading-routine repo receives a push → pulls the repo
and runs the full loader so Postgres (and Metabase) update immediately.

Config via environment variables (loaded from /home/char/workspace/dashboard/.env):
  WEBHOOK_SECRET  — GitHub webhook secret (set in repo Settings → Webhooks)
  WEBHOOK_PORT    — port to listen on (default: 9876)
  PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD — passed through to loader

Security: every request must carry a valid X-Hub-Signature-256 HMAC.
Requests without a valid signature are rejected with 403.
"""
import hashlib
import hmac
import http.server
import json
import logging
import os
import subprocess
import threading
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("webhook")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").encode()
WEBHOOK_PORT   = int(os.environ.get("WEBHOOK_PORT", "9876"))

LOADER_DIR   = Path(__file__).parent.parent / "loader"
REPO_DIR     = Path(__file__).parent.parent.parent / "trading-routine"
ENV_FILE     = Path(__file__).parent.parent / ".env"

# Serialise loader runs — never run two at once.
_loader_lock = threading.Lock()


def _load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def _run_loader() -> None:
    if not _loader_lock.acquire(blocking=False):
        log.warning("Loader already running, skipping this trigger")
        return
    try:
        file_env = _load_env(ENV_FILE)
        env = os.environ.copy()
        env.update({
            "PGHOST":     env.get("PGHOST",     "127.0.0.1"),
            "PGPORT":     env.get("PGPORT",     "5432"),
            "PGDATABASE": env.get("PGDATABASE", "trading"),
            "PGUSER":     file_env.get("POSTGRES_USER",     env.get("PGUSER", "trading")),
            "PGPASSWORD": file_env.get("POSTGRES_PASSWORD", env.get("PGPASSWORD", "")),
        })

        log.info("Pulling trading-routine repo…")
        subprocess.run(
            ["git", "-C", str(REPO_DIR), "pull", "--rebase", "origin", "main"],
            check=True, capture_output=True, text=True,
        )

        log.info("Running loader…")
        result = subprocess.run(
            ["python3", "run.py", "--repo", str(REPO_DIR)],
            cwd=str(LOADER_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log.info("Loader finished OK:\n%s", result.stdout.strip())
        else:
            log.error("Loader failed (rc=%d):\n%s\n%s", result.returncode, result.stdout, result.stderr)
    except Exception as e:
        log.exception("Loader run failed: %s", e)
    finally:
        _loader_lock.release()


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default access log (we use our own)
        pass

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, b"OK")
        else:
            self._respond(404, b"Not found")

    def do_POST(self):
        if self.path != "/webhook":
            self._respond(404, b"Not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Verify HMAC signature
        sig_header = self.headers.get("X-Hub-Signature-256", "")
        if WEBHOOK_SECRET:
            expected = "sha256=" + hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                log.warning("Invalid signature from %s", self.client_address[0])
                self._respond(403, b"Forbidden")
                return

        # Only act on push events
        event = self.headers.get("X-GitHub-Event", "")
        if event not in ("push", "ping"):
            self._respond(200, b"Ignored")
            return

        if event == "ping":
            log.info("GitHub ping received — webhook configured correctly")
            self._respond(200, b"Pong")
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, b"Bad JSON")
            return

        ref   = payload.get("ref", "")
        repo  = payload.get("repository", {}).get("full_name", "")
        log.info("Push to %s %s — triggering loader", repo, ref)

        # Respond immediately so GitHub doesn't time out; run loader in background
        self._respond(200, b"Accepted")
        t = threading.Thread(target=_run_loader, daemon=True)
        t.start()

    def _respond(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("0.0.0.0", WEBHOOK_PORT), WebhookHandler)
    log.info("Webhook server listening on port %d", WEBHOOK_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
