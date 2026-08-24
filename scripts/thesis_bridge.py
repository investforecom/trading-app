#!/usr/bin/env python3
"""
Host-side Thesis bridge — Unix socket server.

Runs `claude -p` (the user's existing Claude Code subscription, same
mechanism as ibkr_bridge.py) to answer the Thesis stage's business
questions and to write the DCF stage's thesis + risks. This keeps LLM
usage inside the Claude subscription instead of requiring a separately
billed Anthropic API key.

Protocol: one JSON request per connection, one JSON response, then close.
  Request:  {"task": "thesis_qa" | "dcf_thesis", ...task-specific fields}
  Response: {"result": {...}} or {"error": "..."}
"""

import json
import os
import re
import socket
import subprocess
import threading

SOCKET_DIR = "/tmp/trading-sockets"
SOCKET_PATH = f"{SOCKET_DIR}/thesis-bridge.sock"
CLAUDE = os.path.expanduser("~/.local/bin/claude")
WORK_DIR = os.path.expanduser("~/workspace")
CLAUDE_TIMEOUT = 150  # seconds

THESIS_QA_SYSTEM = """You are an equity analyst building a short growth thesis for a \
sophisticated individual investor who owns all trading decisions (no disclaimers needed).

You are given the company's Quality Screen fundamentals (reliability, profitability, \
debt, dilution, valuation) already computed by the user's own tool. Base 80-90% of your \
answer directly on these numbers — cite the specific figures that justify each claim. Use \
the WebSearch tool sparingly (at most a few searches) only to fill gaps the fundamentals \
can't answer — e.g. a recent 10-Q/10-K disclosure, a specific competitive development, or a \
demand driver not visible in the financials. Every answer must be justified: reference the \
number or source behind it, not just an assertion.

Classify the company into exactly one stage:
- Growth: revenue still compounding at a high rate, market still being won
- Stabilization: growth decelerating, margins/moat maturing, competitive position settling
- Mature: low growth, capital return focus, moat largely established or eroding

Respond with ONLY a single fenced json code block (```json ... ```) matching this schema — \
no text before or after the fence:
{
  "demand": "1-2 sentences: what is the demand for this business's products/services, grounded in revenue growth and market context",
  "moat": "1-2 sentences: what is the moat (pricing power, switching costs, network effects, scale, IP)",
  "moat_trend": "Widening | Narrowing | Stable",
  "moat_trend_reason": "1 sentence justifying the trend, citing margin/market-share evidence",
  "numbers_support_story": true,
  "numbers_support_reason": "1-2 sentences: do growth/margins/dilution/debt actually back up the narrative, or is there a mismatch",
  "stage": "Growth | Stabilization | Mature",
  "stage_reason": "1 sentence justifying the stage classification",
  "growth_basis": "FCF | Earnings | Sales",
  "growth_rate_pct": 25,
  "growth_years": 5,
  "normalized_growth_pct": 6,
  "thesis_text": "Exactly 2 sentences: (1) 'The business is in the <Stage> stage and should compound <growth_basis> at roughly <growth_rate_pct>% annually for the next <growth_years> years before normalizing to <normalized_growth_pct>%.' (2) One sentence on the core justification.",
  "main_risks": [{"title": "short risk label, max 8 words", "detail": "1-2 sentences justifying it against the specific numbers or narrative above — not generic market risk"}],
  "catalysts": [{"title": "short catalyst label, max 8 words", "timing": "e.g. 'Q2 FY27 earnings, Aug 26 2026' or 'Ongoing' or 'Next 6-12 months' — be as specific as the evidence allows", "detail": "1-2 sentences on what happens and why it matters to this thesis"}],
  "sources_used": ["short label per web search source actually used, e.g. 'Q2 FY26 10-Q' — empty array if none used"]
}
main_risks must have 3-5 items, catalysts must have 2-4 items. Use web search for catalysts \
that need a specific date (next earnings, product launch, regulatory decision) when the \
fundamentals alone don't give one.
"""

DCF_THESIS_SYSTEM = """You are an equity research analyst building an investment thesis for a \
sophisticated individual investor who owns all trading decisions (no disclaimers needed). \
You are given fundamentals for a ticker and a 3-scenario DCF (bear/base/bull) already computed \
by the user's own model. Write a concise, opinionated thesis grounded in the numbers given — \
do not hedge with generic boilerplate. Flag the risks that would actually break this specific \
thesis, not generic market risk.

Respond with ONLY a single fenced json code block (```json ... ```) matching this schema — \
no text before or after the fence:
{
  "thesis_text": "3-6 sentence investment thesis: why this name, why now, what has to be true",
  "top_risks": [{"title": "short risk label, max 8 words", "detail": "1-2 sentence explanation"}],
  "scenario_commentary": {
    "bear": "1-2 sentences: what has to happen for the bear case",
    "base": "1-2 sentences: what has to happen for the base case",
    "bull": "1-2 sentences: what has to happen for the bull case"
  },
  "target_price": 123.45
}
top_risks must have 3-5 items. target_price is a probability-weighted 12-month target, \
informed by the three DCF scenarios and analyst context — not a simple average.
"""


def _run_claude(prompt: str, allowed_tools: str, max_turns: str) -> str:
    proc = subprocess.run(
        [CLAUDE, "--print", "--allowedTools", allowed_tools, "--max-turns", max_turns, prompt],
        capture_output=True, text=True, cwd=WORK_DIR, timeout=CLAUDE_TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exited {proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout


def _extract_json(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in claude output: {text[:300]!r}")
    return json.loads(match.group(1))


def handle_thesis_qa(req: dict) -> dict:
    ticker = req["ticker"]
    fundamentals = req["fundamentals"]
    prompt = f"""{THESIS_QA_SYSTEM}

Ticker: {ticker} ({fundamentals.get("long_name")})
Sector: {fundamentals.get("sector")} / {fundamentals.get("industry")}

Quality Screen fundamentals:
{json.dumps(fundamentals, indent=2, default=str)}

Answer the business questions and produce the growth thesis."""
    output = _run_claude(prompt, allowed_tools="WebSearch", max_turns="8")
    return _extract_json(output)


def handle_dcf_thesis(req: dict) -> dict:
    ticker = req["ticker"]
    fundamentals = req["fundamentals"]
    dcf_outputs = req["dcf_outputs"]
    prompt = f"""{DCF_THESIS_SYSTEM}

Ticker: {ticker}

Fundamentals:
{json.dumps(fundamentals, indent=2, default=str)}

DCF output (bear/base/bull implied prices + assumptions, computed by the user's own model):
{json.dumps({k: v for k, v in dcf_outputs.items() if k != "sensitivity"}, indent=2, default=str)}

Current price: {fundamentals.get("current_price")}

Write the investment thesis."""
    output = _run_claude(prompt, allowed_tools="", max_turns="2")
    return _extract_json(output)


TASKS = {"thesis_qa": handle_thesis_qa, "dcf_thesis": handle_dcf_thesis}


def handle(conn: socket.socket):
    try:
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        req = json.loads(b"".join(chunks).decode())

        handler = TASKS.get(req.get("task"))
        if not handler:
            raise ValueError(f"unknown task {req.get('task')!r}")

        result = handler(req)
        conn.sendall(json.dumps({"result": result}).encode())
    except Exception as exc:
        try:
            conn.sendall(json.dumps({"error": str(exc)}).encode())
        except Exception:
            pass
    finally:
        conn.close()


def main():
    os.makedirs(SOCKET_DIR, exist_ok=True)
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)
    srv.listen(4)
    print(f"Thesis bridge listening on {SOCKET_PATH}", flush=True)

    while True:
        conn, _ = srv.accept()
        t = threading.Thread(target=handle, args=(conn,), daemon=True)
        t.start()


if __name__ == "__main__":
    main()
