import asyncio
import json
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.db import query_one

router = APIRouter()

LOADER_DIR   = "/loader"
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

        # Bridge updated account_state.json → run loader to sync positions
        yield _event({"phase": "Loading positions into DB..."})
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "run.py", "--repo", ROUTINE_DIR,
                cwd=LOADER_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    yield _event({"log": line})
            await proc.wait()
        except FileNotFoundError:
            yield _event({"log": "⚠ Loader not mounted — positions not updated"})

    else:
        # Fallback: no bridge — reload whatever files are already on disk
        yield _event({"log": "⚠ IBKR bridge offline — loading local files only"})
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "run.py", "--repo", ROUTINE_DIR,
                cwd=LOADER_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    yield _event({"log": line})
            await proc.wait()
        except FileNotFoundError:
            yield _event({"error": "Loader not found — volume mounts not ready"})
            return

    # ── Phase 2: force-upsert account snapshot ────────────────────────────────
    yield _event({"phase": "Syncing account snapshot..."})

    state_path = Path(ROUTINE_DIR) / "account_state.json"
    if state_path.exists():
        data = json.loads(state_path.read_text())
        row = query_one(
            """
            INSERT INTO account_snapshots
                (owner_id, account_id, snapshot_date,
                 nav, cash, sgov, deployed_pct, eff_leverage, daily_pnl, updated_at)
            VALUES (1, 1, %(date)s,
                    %(nav)s, %(cash)s, %(sgov)s, %(deployed_pct)s, %(leverage)s,
                    %(daily_pnl)s, NOW())
            ON CONFLICT (account_id, snapshot_date) DO UPDATE SET
                nav          = EXCLUDED.nav,
                cash         = EXCLUDED.cash,
                sgov         = EXCLUDED.sgov,
                deployed_pct = EXCLUDED.deployed_pct,
                eff_leverage = EXCLUDED.eff_leverage,
                daily_pnl    = EXCLUDED.daily_pnl,
                updated_at   = NOW()
            RETURNING snapshot_date, nav, daily_pnl, updated_at
            """,
            {
                "date":         data.get("date"),
                "nav":          data.get("nav"),
                "cash":         data.get("cash"),
                "sgov":         data.get("sgov"),
                "deployed_pct": data.get("deployed_pct"),
                "leverage":     data.get("leverage"),
                "daily_pnl":    data.get("daily_pnl"),
            },
        )
        if row:
            ts = row["updated_at"].strftime("%d %b %H:%M") if row["updated_at"] else "—"
            yield _event({"log": f"  snapshot {row['snapshot_date']} → NAV ${row['nav']:,.0f} (at {ts})"})

    # ── Phase 2b: load AI interpretations ────────────────────────────────────
    ai_notes_path = Path(ROUTINE_DIR) / "position_ai_notes.json"
    if ai_notes_path.exists():
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
            yield _event({"log": f"  AI notes written for {updated} positions ✓"})

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
