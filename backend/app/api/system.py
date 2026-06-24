import asyncio
import json
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.db import query_one

router = APIRouter()

ROUTINE_DIR  = "/trading-routine"
SOCKET_PATH  = "/tmp/trading-sockets/ibkr-refresh.sock"


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _bridge_available() -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(SOCKET_PATH), timeout=2
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def _stream_refresh():
    bridge_up = await _bridge_available()

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    if bridge_up:
        # Live pull: host claude agent → IBKR MCP → writes account_state.json
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
            yield _event({"error": "IBKR pull failed — check bridge logs"})
            return

    else:
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
    running = await _bridge_available()
    return {"running": running}
