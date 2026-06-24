#!/usr/bin/env python3
"""
Deterministic positions updater — writes directly to Postgres.

Reads ibkr_positions.json + account_state.json (local temp files written by
the bridge's claude -p step), then:
  1. Upserts account_snapshots with today's NAV / cash / P&L
  2. Matches each open DB position against live IBKR data
  3. Upserts position_snapshots (current_value / gain_pct / pct_nav for today)

No CSV, no git. The DB is the single source of truth.

Env / connection: reads TRADING_APP_DIR from environment (defaults to
~/workspace/trading-app) to find the .env file for PG credentials.
Alternatively set PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE directly.
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extras

ROUTINE_DIR = Path.home() / "workspace" / "trading-routine"
APP_DIR     = Path(os.environ.get("TRADING_APP_DIR", Path.home() / "workspace" / "trading-app"))


# ── DB connection ─────────────────────────────────────────────────────────────

def _load_env(app_dir: Path) -> dict:
    """Parse key=value pairs from .env, skip comments."""
    env: dict = {}
    env_path = app_dir / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                # Strip inline comments
                v = v.split("#")[0].strip()
                env[k.strip()] = v
    return env


def _connect(app_dir: Path = APP_DIR):
    env = _load_env(app_dir)
    return psycopg2.connect(
        host    = os.environ.get("PGHOST",     env.get("PGHOST",     "127.0.0.1")),
        port    = int(os.environ.get("PGPORT", env.get("PGPORT",     "5432"))),
        dbname  = os.environ.get("PGDATABASE", env.get("PGDATABASE", "trading")),
        user    = os.environ.get("PGUSER",     env.get("PGUSER",     env.get("POSTGRES_USER", "trading"))),
        password= os.environ.get("PGPASSWORD", env.get("PGPASSWORD", env.get("POSTGRES_PASSWORD", ""))),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ── IBKR data indexing ───────────────────────────────────────────────────────

def index_ibkr_positions(positions: list[dict]) -> tuple[dict, dict, dict]:
    """
    Build lookup dicts from raw IBKR position list.

    stocks:   ticker → market_value (native currency; GBP needs conversion)
    opts:     (underlying, year2, strike, "CALL"|"PUT") → market_value USD
    opts_day: (underlying, mon3, day2, strike, "CALL"|"PUT") → market_value
              for weeklies like "ONDS Jul02'26 10.5 CALL"
    """
    stocks:   dict[str, float] = {}
    opts:     dict[tuple, float] = {}
    opts_day: dict[tuple, float] = {}

    OPT_RE = re.compile(r"(\w+)\s+([A-Za-z]{3})(\d{2})'(\d{2})\s+([\d.]+)\s+(CALL|PUT)")

    for p in positions:
        desc  = p["contract_description"]
        asset = p["asset_class"]
        mv    = float(p["market_value"])

        if asset == "STK":
            ticker = desc.split()[0]
            stocks[ticker] = stocks.get(ticker, 0.0) + mv

        elif asset == "OPT":
            m = OPT_RE.match(desc)
            if m:
                und    = m.group(1).upper()
                mon3   = m.group(2).upper()   # "JUL"
                day2   = m.group(3)           # "02"
                year2  = m.group(4)           # "26"
                strike = m.group(5)           # "10.5"
                cp     = m.group(6)           # "CALL"
                opts[(und, year2, strike, cp)]             = opts.get((und, year2, strike, cp), 0.0) + mv
                opts_day[(und, mon3, day2, strike, cp)]   = opts_day.get((und, mon3, day2, strike, cp), 0.0) + mv

    return stocks, opts, opts_day


def resolve_current_value(
    symbol: str,
    strategy: str,
    underlying: str,
    stocks: dict,
    opts: dict,
    opts_day: dict,
    fx_gbp: float = 1.32,
) -> float | None:
    """
    Return live current_value for a position row, or None if no IBKR match.

    Convention (matches existing DB / CSV convention):
      - Long positions:  current_value = market_value (positive)
      - Short options:   current_value = abs(market_value) — the buyback cost
      - Spreads:         current_value = sum of both legs (net value, can be small)
    """
    STOCK_STRATEGIES = {"Thematic", "2x-ETF", "cash"}
    sym   = symbol.upper()
    parts = sym.split("_")

    is_stock = (
        strategy in STOCK_STRATEGIES
        or len(parts) < 2
        or (len(parts) == 2 and parts[-1] == "STK")
        or (len(parts) >= 2 and not re.search(r"\d", parts[-1]))
    )

    if is_stock:
        mv = stocks.get(underlying)
        if mv is None:
            return None
        # IQE trades on LSE in GBP — apply FX
        return mv * fx_gbp if underlying == "IQE" else mv

    if len(parts) < 3:
        return None

    und   = parts[0]
    monyy = parts[1]
    year2 = monyy[3:]

    # Parse strikes from last segment: "170C270C" → [(170,CALL),(270,CALL)]
    legs = [(s, "CALL" if t == "C" else "PUT") for s, t in re.findall(r"([\d.]+)([CP])", parts[2])]

    if not legs:
        return None

    if len(legs) == 1:
        strike, cp = legs[0]
        mv = opts.get((und, year2, strike, cp))
        if mv is None:
            # Try day-based key for weeklies (e.g. ONDS_JUL02_10.5C)
            mon3 = monyy[:3].upper()
            mv = opts_day.get((und, mon3, year2, strike, cp))
        if mv is None:
            return None
        return abs(mv) if mv < 0 else mv
    else:
        total   = 0.0
        matched = 0
        for strike, cp in legs:
            mv = opts.get((und, year2, strike, cp))
            if mv is not None:
                total += mv
                matched += 1
        return total if matched > 0 else None


# ── DB upserts ───────────────────────────────────────────────────────────────

def upsert_account_snapshot(cur, state: dict, account_id: int = 1, owner_id: int = 1):
    cur.execute("""
        INSERT INTO account_snapshots
            (owner_id, account_id, snapshot_date,
             nav, cash, sgov, deployed_pct, eff_leverage, daily_pnl, updated_at)
        VALUES
            (%(owner_id)s, %(account_id)s, %(date)s,
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
        RETURNING snapshot_date, nav
    """, {**state, "owner_id": owner_id, "account_id": account_id})
    row = cur.fetchone()
    print(f"  account_snapshot {row['snapshot_date']} → NAV ${row['nav']:,.0f} ✓")


def upsert_position_snapshots(
    cur,
    positions_db: list[dict],
    stocks: dict,
    opts: dict,
    opts_day: dict,
    nav: float,
    today: str,
    fx_gbp: float,
    owner_id: int = 1,
) -> tuple[int, int]:
    updated = 0
    missed  = 0

    for pos in positions_db:
        pid        = pos["id"]
        symbol     = pos["symbol"]
        strategy   = pos["strategy"]
        underlying = pos["underlying"]
        cost_basis = float(pos["cost_basis"] or 0)
        qty        = int(pos["qty"] or 0)

        cv = resolve_current_value(symbol, strategy, underlying, stocks, opts, opts_day, fx_gbp)
        if cv is None:
            missed += 1
            continue

        if qty < 0:
            gain_pct = round((cost_basis - cv) / abs(cost_basis) * 100, 4) if cost_basis else 0
        else:
            gain_pct = round((cv - cost_basis) / abs(cost_basis) * 100, 4) if cost_basis else 0

        pct_nav = round(cv / nav * 100, 4) if nav else 0

        cur.execute("""
            INSERT INTO position_snapshots
                (position_id, owner_id, snapshot_date,
                 qty, cost_basis, current_value, gain_pct, pct_nav,
                 forward_rr, max_value, mgmt_tier, quality_rank, flags, notes)
            SELECT
                %(position_id)s, %(owner_id)s, %(snapshot_date)s,
                %(qty)s, %(cost_basis)s, %(current_value)s, %(gain_pct)s, %(pct_nav)s,
                forward_rr, max_value, mgmt_tier, quality_rank, flags, notes
            FROM position_snapshots
            WHERE position_id = %(position_id)s
            ORDER BY snapshot_date DESC
            LIMIT 1
            ON CONFLICT (position_id, snapshot_date) DO UPDATE SET
                current_value = EXCLUDED.current_value,
                gain_pct      = EXCLUDED.gain_pct,
                pct_nav       = EXCLUDED.pct_nav,
                qty           = EXCLUDED.qty,
                cost_basis    = EXCLUDED.cost_basis
        """, {
            "position_id":   pid,
            "owner_id":      owner_id,
            "snapshot_date": today,
            "qty":           qty,
            "cost_basis":    cost_basis,
            "current_value": round(cv, 2),
            "gain_pct":      gain_pct,
            "pct_nav":       pct_nav,
        })
        updated += 1

    return updated, missed


# ── Main ─────────────────────────────────────────────────────────────────────

def run(routine_dir: Path = ROUTINE_DIR) -> bool:
    state_path = routine_dir / "account_state.json"
    ibkr_path  = routine_dir / "ibkr_positions.json"

    if not state_path.exists():
        print("ERROR: account_state.json not found", file=sys.stderr)
        return False
    if not ibkr_path.exists():
        print("ERROR: ibkr_positions.json not found", file=sys.stderr)
        return False

    state     = json.loads(state_path.read_text())
    nav       = float(state["nav"])
    today     = state.get("date") or date.today().isoformat()
    fx_gbp    = float(state.get("fx_gbp", 1.32))
    positions_raw = json.loads(ibkr_path.read_text())["positions"]

    stocks, opts, opts_day = index_ibkr_positions(positions_raw)

    conn = _connect()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # 1. Account snapshot
            upsert_account_snapshot(cur, state)

            # 2. Load open positions metadata from DB
            cur.execute("""
                SELECT p.id, p.symbol, p.underlying, p.strategy,
                       ps.cost_basis, ps.qty
                FROM positions p
                JOIN accounts a ON a.id = p.account_id
                JOIN position_snapshots ps ON ps.position_id = p.id
                WHERE a.ibkr_account_id = 'U15760849'
                  AND p.closed_date IS NULL
                  AND ps.snapshot_date = (
                      SELECT MAX(snapshot_date) FROM position_snapshots
                  )
                ORDER BY p.symbol
            """)
            positions_db = list(cur.fetchall())

            # 3. Match and upsert snapshots for today
            updated, missed = upsert_position_snapshots(
                cur, positions_db, stocks, opts, opts_day, nav, today, fx_gbp
            )

        print(f"  positions: {updated} updated, {missed} no IBKR match")
        print(f"  snapshot date: {today}")
        return True

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
