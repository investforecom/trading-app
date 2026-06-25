#!/usr/bin/env python3
"""
Deterministic positions updater — writes directly to Postgres.

Reads ibkr_positions.json + account_state.json (local temp files written by
the bridge's claude -p step), then:
  1. Upserts account_snapshots with today's NAV / cash / P&L
  2. Matches each open DB position against live IBKR data, updating
     current_value, gain_pct, pct_nav, AND qty (from IBKR, not DB)
  3. Auto-creates new positions for short options in IBKR that have no DB row
     (strategy inferred: short PUT → WheelSP, short CALL → WheelSC)

No CSV, no git. The DB is the single source of truth.
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).parent))
import routine_log as rlog

ROUTINE_DIR = Path.home() / "workspace" / "trading-routine"
APP_DIR     = Path(os.environ.get("TRADING_APP_DIR", Path.home() / "workspace" / "trading-app"))

OPT_RE = re.compile(r"(\w+)\s+([A-Za-z]{3})(\d{2})'(\d{2})\s+([\d.]+)\s+(CALL|PUT)")


# ── DB connection ─────────────────────────────────────────────────────────────

def _load_env(app_dir: Path) -> dict:
    env: dict = {}
    env_path = app_dir / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                v = v.split("#")[0].strip()
                env[k.strip()] = v
    return env


def _connect(app_dir: Path = APP_DIR):
    env = _load_env(app_dir)
    return psycopg2.connect(
        host     = os.environ.get("PGHOST",     env.get("PGHOST",     "127.0.0.1")),
        port     = int(os.environ.get("PGPORT", env.get("PGPORT",     "5432"))),
        dbname   = os.environ.get("PGDATABASE", env.get("PGDATABASE", "trading")),
        user     = os.environ.get("PGUSER",     env.get("PGUSER",     env.get("POSTGRES_USER", "trading"))),
        password = os.environ.get("PGPASSWORD", env.get("PGPASSWORD", env.get("POSTGRES_PASSWORD", ""))),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ── IBKR data indexing ───────────────────────────────────────────────────────

def index_ibkr_positions(positions: list[dict]) -> tuple[dict, dict, dict]:
    """
    Build lookup dicts from raw IBKR position list.

    Each dict value is {"mv": float, "qty": int} where qty is signed
    (positive = long, negative = short) from the IBKR position field.

    stocks:   ticker → {mv, qty}
    opts:     (underlying, year2, strike, CP) → {mv, qty}
    opts_day: (underlying, mon3, day2, strike, CP) → {mv, qty}  ← weeklies
    """
    stocks:   dict[str, dict] = {}
    opts:     dict[tuple, dict] = {}
    opts_day: dict[tuple, dict] = {}

    for p in positions:
        desc    = p["contract_description"]
        asset   = p["asset_class"]
        mv      = float(p["market_value"])
        ibkr_qty = int(float(p.get("position", 0) or 0))

        if asset == "STK":
            ticker = desc.split()[0]
            if ticker not in stocks:
                stocks[ticker] = {"mv": 0.0, "qty": 0}
            stocks[ticker]["mv"]  += mv
            stocks[ticker]["qty"] += ibkr_qty

        elif asset == "OPT":
            m = OPT_RE.match(desc)
            if m:
                und    = m.group(1).upper()
                mon3   = m.group(2).upper()
                day2   = m.group(3)
                year2  = m.group(4)
                strike = m.group(5)
                cp     = m.group(6)

                key_yr  = (und, year2, strike, cp)
                key_day = (und, mon3, day2, strike, cp)

                for key, d in [(key_yr, opts), (key_day, opts_day)]:
                    if key not in d:
                        d[key] = {"mv": 0.0, "qty": 0}
                    d[key]["mv"]  += mv
                    d[key]["qty"] += ibkr_qty

    return stocks, opts, opts_day


def resolve_current_value(
    symbol: str,
    strategy: str,
    underlying: str,
    stocks: dict,
    opts: dict,
    opts_day: dict,
    fx_gbp: float = 1.32,
    consumed: set | None = None,
) -> tuple[float | None, int | None]:
    """
    Return (current_value, ibkr_qty) for a position, or (None, None) if no match.

    ibkr_qty is the live contract/share count from IBKR (always positive; the
    sign is conveyed by the position's qty column in the DB).

    Keys consumed during matching are added to the `consumed` set so
    auto_create_missing_options can skip them.
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
        entry = stocks.get(underlying)
        if entry is None:
            return None, None
        mv  = entry["mv"]
        qty = abs(entry["qty"])
        cv  = mv * fx_gbp if underlying == "IQE" else mv
        return cv, qty

    if len(parts) < 3:
        return None, None

    und   = parts[0]
    monyy = parts[1]
    year2 = monyy[3:]

    legs = [(s, "CALL" if t == "C" else "PUT") for s, t in re.findall(r"([\d.]+)([CP])", parts[2])]
    if not legs:
        return None, None

    if len(legs) == 1:
        strike, cp = legs[0]
        key_yr  = (und, year2, strike, cp)
        entry   = opts.get(key_yr)
        hit_key = key_yr

        if entry is None:
            mon3    = monyy[:3].upper()
            key_day = (und, mon3, year2, strike, cp)
            entry   = opts_day.get(key_day)
            hit_key = key_day

        if entry is None:
            return None, None

        if consumed is not None:
            consumed.add(hit_key)

        mv  = entry["mv"]
        qty = abs(entry["qty"])
        return abs(mv) if mv < 0 else mv, qty

    else:
        # Spread: sum legs, take qty from first matched leg
        total   = 0.0
        matched = 0
        qty     = None
        for strike, cp in legs:
            key = (und, year2, strike, cp)
            entry = opts.get(key)
            if entry is not None:
                total   += entry["mv"]
                matched += 1
                if qty is None:
                    qty = abs(entry["qty"])
                if consumed is not None:
                    consumed.add(key)
        return (total, qty) if matched > 0 else (None, None)


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
    msg = f"account_snapshot {row['snapshot_date']} → NAV ${row['nav']:,.0f} ✓"
    print(f"  {msg}")
    rlog.ok(msg)


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
) -> tuple[int, int, set]:
    """
    Returns (updated, missed, consumed_keys).
    consumed_keys: IBKR opt index keys matched to existing DB positions.
    """
    updated  = 0
    missed   = 0
    consumed: set = set()

    for pos in positions_db:
        pid        = pos["id"]
        symbol     = pos["symbol"]
        strategy   = pos["strategy"]
        underlying = pos["underlying"]
        cost_basis = float(pos["cost_basis"] or 0)
        db_qty     = int(pos["qty"] or 0)

        cv, ibkr_qty = resolve_current_value(
            symbol, strategy, underlying, stocks, opts, opts_day, fx_gbp, consumed
        )
        if cv is None:
            missed += 1
            continue

        # Use live IBKR qty; fall back to DB qty if IBKR didn't return one
        qty = ibkr_qty if ibkr_qty is not None else abs(db_qty)
        # Preserve sign from DB (short positions are negative)
        if db_qty < 0:
            qty = -qty

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

    return updated, missed, consumed


def auto_create_missing_options(
    cur,
    positions_raw: list[dict],
    consumed: set,
    nav: float,
    today: str,
    account_id: int = 1,
    owner_id: int = 1,
) -> int:
    """
    Create position + snapshot rows for IBKR options with no DB entry.

    Pass 1 — Pair detection: groups unmatched options by (und, mon3, day2, year2).
      Long lower-strike CALL + short higher-strike CALL → LDS (call debit spread)
      Short higher-strike PUT  + long lower-strike PUT  → LDS (put debit spread)
    Pass 2 — Standalone shorts: remaining unmatched short options → WheelSP / WheelSC.
    Unpaired long options are skipped (may be LEAPS already in DB or already closed legs).
    """
    def _fmt(strike: str) -> str:
        try:
            f = float(strike)
            return str(int(f)) if f == int(f) else strike
        except ValueError:
            return strike

    # ── Collect all unmatched options (long + short) ─────────────────────────
    unmatched: list[dict] = []
    for p in positions_raw:
        if p["asset_class"] != "OPT":
            continue
        desc = p["contract_description"]
        m = OPT_RE.match(desc)
        if not m:
            continue
        und, mon3, day2, year2, strike, cp = (
            m.group(1).upper(), m.group(2).upper(), m.group(3),
            m.group(4), m.group(5), m.group(6),
        )
        key_yr  = (und, year2, strike, cp)
        key_day = (und, mon3, day2, strike, cp)
        if key_yr in consumed or key_day in consumed:
            continue
        unmatched.append({
            "und": und, "mon3": mon3, "day2": day2, "year2": year2,
            "strike": strike, "cp": cp,
            "key_yr": key_yr, "key_day": key_day,
            "ibkr_qty":  int(float(p.get("position",      0) or 0)),
            "avg_price": float(p.get("average_price",  0) or 0),
            "mv":        float(p["market_value"]),
        })

    # ── Pass 1: detect spread pairs ───────────────────────────────────────────
    groups: dict = defaultdict(list)
    for opt in unmatched:
        groups[(opt["und"], opt["mon3"], opt["day2"], opt["year2"])].append(opt)

    pair_consumed: set   = set()
    to_create:     list  = []

    for (und, mon3, day2, year2), group in groups.items():
        calls = [o for o in group if o["cp"] == "CALL"]
        puts  = [o for o in group if o["cp"] == "PUT"]

        long_calls  = sorted([o for o in calls if o["ibkr_qty"] > 0], key=lambda x: float(x["strike"]))
        short_calls = sorted([o for o in calls if o["ibkr_qty"] < 0], key=lambda x: float(x["strike"]))
        long_puts   = sorted([o for o in puts  if o["ibkr_qty"] > 0], key=lambda x: float(x["strike"]))
        short_puts  = sorted([o for o in puts  if o["ibkr_qty"] < 0], key=lambda x: float(x["strike"]))

        paired_lc: set = set()
        paired_sc: set = set()
        for lc in long_calls:
            if lc["key_yr"] in paired_lc:
                continue
            for sc in short_calls:
                if sc["key_yr"] in paired_sc:
                    continue
                if float(lc["strike"]) < float(sc["strike"]):
                    abs_qty   = min(abs(lc["ibkr_qty"]), abs(sc["ibkr_qty"]))
                    net_debit = (lc["avg_price"] - sc["avg_price"]) * abs_qty * 100
                    net_mv    = lc["mv"] + sc["mv"]
                    lo, hi    = sorted([lc["strike"], sc["strike"]], key=float)
                    symbol    = f"{und}_{mon3}{year2}_{_fmt(lo)}C{_fmt(hi)}C"
                    cost      = round(net_debit, 2) if net_debit > 0 else round(abs(net_mv), 2)
                    to_create.append({
                        "symbol": symbol, "underlying": und, "strategy": "LDS",
                        "abs_qty": abs_qty, "cost_basis": cost, "current_value": round(net_mv, 2),
                        "is_short": False,
                    })
                    pair_consumed.update({lc["key_yr"], sc["key_yr"]})
                    paired_lc.add(lc["key_yr"])
                    paired_sc.add(sc["key_yr"])
                    break

        paired_lp: set = set()
        paired_sp: set = set()
        for sp in short_puts:
            if sp["key_yr"] in paired_sp:
                continue
            for lp in long_puts:
                if lp["key_yr"] in paired_lp:
                    continue
                if float(sp["strike"]) > float(lp["strike"]):
                    abs_qty   = min(abs(sp["ibkr_qty"]), abs(lp["ibkr_qty"]))
                    net_debit = (lp["avg_price"] - sp["avg_price"]) * abs_qty * 100
                    net_mv    = sp["mv"] + lp["mv"]
                    lo, hi    = sorted([sp["strike"], lp["strike"]], key=float)
                    symbol    = f"{und}_{mon3}{year2}_{_fmt(lo)}P{_fmt(hi)}P"
                    cost      = round(abs(net_debit), 2) if net_debit != 0 else round(abs(net_mv), 2)
                    to_create.append({
                        "symbol": symbol, "underlying": und, "strategy": "LDS",
                        "abs_qty": abs_qty, "cost_basis": cost, "current_value": round(net_mv, 2),
                        "is_short": False,
                    })
                    pair_consumed.update({sp["key_yr"], lp["key_yr"]})
                    paired_sp.add(sp["key_yr"])
                    paired_lp.add(lp["key_yr"])
                    break

    # ── Pass 2: standalone short options not paired into spreads ──────────────
    for opt in unmatched:
        if opt["key_yr"] in pair_consumed:
            continue
        if opt["ibkr_qty"] >= 0:
            continue  # skip unpaired long options
        consumed.add(opt["key_yr"])
        consumed.add(opt["key_day"])
        cp_char  = "C" if opt["cp"] == "CALL" else "P"
        symbol   = f"{opt['und']}_{opt['mon3']}{opt['day2']}_{_fmt(opt['strike'])}{cp_char}"
        strategy = "WheelSP" if opt["cp"] == "PUT" else "WheelSC"
        abs_qty  = abs(opt["ibkr_qty"])
        avg      = opt["avg_price"]
        mv       = opt["mv"]
        cost_basis    = round(avg * abs_qty * 100, 2) if avg > 0 else round(abs(mv), 2)
        current_value = round(abs(mv), 2)
        to_create.append({
            "symbol": symbol, "underlying": opt["und"], "strategy": strategy,
            "abs_qty": abs_qty, "cost_basis": cost_basis, "current_value": current_value,
            "is_short": True,
        })

    # ── Insert all new positions ───────────────────────────────────────────────
    created = 0
    for item in to_create:
        symbol        = item["symbol"]
        underlying    = item["underlying"]
        strategy      = item["strategy"]
        abs_qty       = item["abs_qty"]
        cost_basis    = item["cost_basis"]
        current_value = item["current_value"]
        is_short      = item["is_short"]

        db_qty = -abs_qty if is_short else abs_qty
        if cost_basis:
            gain_pct = round(
                (cost_basis - current_value) / cost_basis * 100 if is_short
                else (current_value - cost_basis) / cost_basis * 100,
                4,
            )
        else:
            gain_pct = 0
        pct_nav = round(abs(current_value) / nav * 100, 4) if nav else 0

        cur.execute("""
            INSERT INTO positions
                (owner_id, account_id, symbol, underlying, strategy,
                 opened_date, qty_at_open, cost_basis_at_open, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ibkr-auto')
            ON CONFLICT (account_id, symbol) WHERE closed_date IS NULL DO NOTHING
            RETURNING id
        """, (owner_id, account_id, symbol, underlying, strategy,
              today, abs_qty, cost_basis))
        row = cur.fetchone()

        if row is None:
            cur.execute("""
                SELECT id FROM positions
                WHERE account_id = %s AND symbol = %s AND closed_date IS NULL
            """, (account_id, symbol))
            row = cur.fetchone()
            if row is None:
                continue

        position_id = row["id"]
        cur.execute("""
            INSERT INTO position_snapshots
                (position_id, owner_id, snapshot_date,
                 qty, cost_basis, current_value, gain_pct, pct_nav)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (position_id, snapshot_date) DO UPDATE SET
                current_value = EXCLUDED.current_value,
                gain_pct      = EXCLUDED.gain_pct,
                pct_nav       = EXCLUDED.pct_nav,
                qty           = EXCLUDED.qty
        """, (position_id, owner_id, today,
              db_qty, cost_basis, abs(current_value), gain_pct, pct_nav))

        msg = f"auto-created: {symbol} | strategy={strategy} | qty={abs_qty} | cost_basis=${cost_basis:.2f}"
        print(f"  {msg}")
        rlog.ok(msg)
        created += 1

    return created


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

    state         = json.loads(state_path.read_text())
    nav           = float(state["nav"])
    today         = state.get("date") or date.today().isoformat()
    fx_gbp        = float(state.get("fx_gbp", 1.32))
    positions_raw = json.loads(ibkr_path.read_text())["positions"]

    stocks, opts, opts_day = index_ibkr_positions(positions_raw)

    conn = _connect()
    try:
        with conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            upsert_account_snapshot(cur, state)

            # Load open positions from DB (most recent snapshot for cost_basis ref)
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

            updated, missed, consumed = upsert_position_snapshots(
                cur, positions_db, stocks, opts, opts_day, nav, today, fx_gbp
            )

            created = auto_create_missing_options(
                cur, positions_raw, consumed, nav, today
            )

        msg = f"positions: {updated} updated, {created} auto-created, {missed} no IBKR match"
        print(f"  {msg}")
        print(f"  snapshot date: {today}")
        rlog.ok(msg)
        if missed:
            rlog.warn(f"{missed} position(s) had no IBKR match — check symbol mapping")
        return True

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        rlog.error(str(e))
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
