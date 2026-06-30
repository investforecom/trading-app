import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from app.db import query_one

router = APIRouter()

ROUTINE_DIR  = "/trading-routine"
SOCKET_PATH  = "/tmp/trading-sockets/ibkr-refresh.sock"
LOG_PATH     = Path("/app/logs/routine.log")


def _log(tag: str, msg: str) -> None:
    """Write a structured log entry from the API container."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] [{tag:<7}] {msg}\n")


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _bridge_available() -> bool:
    return Path(SOCKET_PATH).exists()


async def _stream_refresh():
    import time
    t0 = time.monotonic()
    _log("START  ", "══════════════════════════════════════════════════")
    _log("START  ", "RUN START  source=manual")

    bridge_up = _bridge_available()

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    if bridge_up:
        _log("PHASE  ", "── IBKR Fetch + DB Sync")
        yield _event({"phase": "Connecting to IBKR..."})
        bridge_ok = False

        try:
            reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
            async for raw in reader:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get("done"):
                        bridge_ok = True
                        yield _event({"log": "IBKR data fetched ✓"})
                    elif ev.get("error"):
                        yield _event({"error": ev["error"]})
                    elif ev.get("log"):
                        yield _event({"log": ev["log"]})
                    elif ev.get("phase"):
                        yield _event({"phase": ev["phase"]})
                except json.JSONDecodeError:
                    if line:
                        yield _event({"log": line})
            writer.close()
            await writer.wait_closed()
        except Exception as exc:
            yield _event({"log": f"Bridge error: {exc}"})

        if not bridge_ok:
            _log("ERROR  ", "IBKR pull failed")
            _log("END    ", f"RUN END    status=ERROR  elapsed={time.monotonic()-t0:.0f}s")
            _log("END    ", "══════════════════════════════════════════════════")
            yield _event({"error": "IBKR pull failed — check bridge logs"})
            return

    else:
        _log("ERROR  ", "IBKR bridge offline")
        _log("END    ", f"RUN END    status=ERROR  elapsed={time.monotonic()-t0:.0f}s")
        _log("END    ", "══════════════════════════════════════════════════")
        yield _event({"log": "⚠ IBKR bridge offline — data not refreshed"})
        return

    # ── Phase 2: apply any completed AI notes ────────────────────────────────
    # sync_positions.py (run inside the bridge) already wrote account + positions
    # to DB. We just pick up AI notes if the background thread finished them.
    ai_notes_path = Path(ROUTINE_DIR) / "position_ai_notes.json"
    if ai_notes_path.exists():
        try:
            ai_notes = json.loads(ai_notes_path.read_text())
            updated = 0
            for symbol, note in ai_notes.items():
                result = query_one(
                    """
                    UPDATE position_snapshots ps
                    SET ai_note = %(note)s
                    FROM positions p
                    WHERE ps.position_id = p.id
                      AND p.symbol       = %(symbol)s
                      AND ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
                    RETURNING ps.snapshot_date
                    """,
                    {"symbol": symbol, "note": note},
                )
                if result:
                    updated += 1
            if updated:
                yield _event({"log": f"AI notes applied for {updated} positions ✓"})
        except Exception:
            pass

    _log("END    ", f"RUN END    status=OK  elapsed={time.monotonic()-t0:.0f}s")
    _log("END    ", "══════════════════════════════════════════════════")
    yield _event({"phase": "Done", "done": True})


@router.get("/refresh/stream")
async def refresh_stream():
    """SSE endpoint: live IBKR pull (via host bridge) then DB sync."""
    return StreamingResponse(
        _stream_refresh(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/bridge/status")
async def bridge_status():
    running = _bridge_available()
    return {"running": running}


@router.get("/logs")
async def get_routine_logs(lines: int = Query(default=200, le=2000)):
    """
    Return the last N lines of routine.log for admin monitoring.

    Each line is a structured entry:
      [2026-06-24T20:05:01Z] [PHASE  ] ── IBKR Fetch
      [2026-06-24T20:05:45Z] [OK     ] positions: 42 updated, 0 no IBKR match
      [2026-06-24T20:06:31Z] [END    ] RUN END    status=OK  elapsed=90s

    Tags to watch: ERROR, WARN → problem indicators.
    Tags START/END → run boundaries with source (manual/cron) and elapsed time.
    """
    if not LOG_PATH.exists():
        return {"lines": [], "running": False, "last_run": None, "last_status": None}

    text = LOG_PATH.read_text(errors="replace")
    all_lines = text.splitlines()

    # Detect if a run is currently in progress (START without subsequent END)
    running = False
    last_run = None
    last_status = None
    for line in reversed(all_lines):
        if "RUN END" in line:
            last_status = "OK" if "status=OK" in line else "ERROR"
            last_run = line
            break
        if "RUN START" in line:
            running = True
            last_run = line
            break

    return {
        "lines": all_lines[-lines:],
        "total_lines": len(all_lines),
        "running": running,
        "last_run": last_run,
        "last_status": last_status,
    }
