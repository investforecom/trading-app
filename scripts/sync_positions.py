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

# ── Theme classification ───────────────────────────────────────────────────────
# Maps underlying ticker → theme. Used when auto-creating positions so every
# new row lands in a theme from day one. Extend this dict as new tickers appear;
# anything not listed falls back to "Miscellaneous".
THEME_MAP: dict[str, str] = {
    # ── AI-Infrastructure ────────────────────────────────────────────────────
    # GPUs, accelerators, data-center supply chain, semis, compute mining
    "NVDA": "AI-Infrastructure", "NVDL": "AI-Infrastructure", "AMD":  "AI-Infrastructure",
    "SMCI": "AI-Infrastructure", "VRT":  "AI-Infrastructure", "AMKR": "AI-Infrastructure",
    "DRAM": "AI-Infrastructure", "FPS":  "AI-Infrastructure", "OSS":  "AI-Infrastructure",
    "CRDO": "AI-Infrastructure", "AVGG": "AI-Infrastructure", "CIFR": "AI-Infrastructure",
    "CLS":  "AI-Infrastructure", "ARM":  "AI-Infrastructure", "MRVL": "AI-Infrastructure",
    "ALAB": "AI-Infrastructure", "INTC": "AI-Infrastructure", "MU":   "AI-Infrastructure",
    "TSM":  "AI-Infrastructure", "KLAC": "AI-Infrastructure", "LRCX": "AI-Infrastructure",
    "AMAT": "AI-Infrastructure", "ASML": "AI-Infrastructure", "ON":   "AI-Infrastructure",
    "MPWR": "AI-Infrastructure", "ENTG": "AI-Infrastructure", "AMBA": "AI-Infrastructure",
    "ACLS": "AI-Infrastructure", "RMBS": "AI-Infrastructure", "SWKS": "AI-Infrastructure",
    "QRVO": "AI-Infrastructure", "ONTO": "AI-Infrastructure", "WOLF": "AI-Infrastructure",
    "CEVA": "AI-Infrastructure", "SOUN": "AI-Infrastructure", "BBAI": "AI-Infrastructure",
    # Bitcoin mining / HPC compute (AI workloads)
    "MARA": "AI-Infrastructure", "RIOT": "AI-Infrastructure", "CLSK": "AI-Infrastructure",
    "CORZ": "AI-Infrastructure", "HUT":  "AI-Infrastructure", "HIVE": "AI-Infrastructure",
    "BTBT": "AI-Infrastructure",
    # Semiconductor ETFs
    "SMH":  "AI-Infrastructure", "SOXX": "AI-Infrastructure", "SOXL": "AI-Infrastructure",

    # ── Cloud-Compute ────────────────────────────────────────────────────────
    # Hyperscale cloud, AI compute platforms, HPC, cloud-native SaaS infra
    "CRWV": "Cloud-Compute", "IREN":  "Cloud-Compute", "ORCL": "Cloud-Compute",
    "MSFT": "Cloud-Compute", "SNOW":  "Cloud-Compute", "DDOG": "Cloud-Compute",
    "NET":  "Cloud-Compute", "CFLT":  "Cloud-Compute", "MDB":  "Cloud-Compute",
    "ZS":   "Cloud-Compute", "PANW":  "Cloud-Compute", "CRWD": "Cloud-Compute",
    "OKTA": "Cloud-Compute", "GTLB":  "Cloud-Compute", "ESTC": "Cloud-Compute",
    "IBM":  "Cloud-Compute", "HUBS":  "Cloud-Compute", "TWLO": "Cloud-Compute",

    # ── Large-Cap-Tech ───────────────────────────────────────────────────────
    # Mega-cap tech and their leveraged / index ETF proxies
    "AMZN": "Large-Cap-Tech", "AAPL": "Large-Cap-Tech", "GOOGL": "Large-Cap-Tech",
    "GOOG": "Large-Cap-Tech", "META": "Large-Cap-Tech", "TSLA":  "Large-Cap-Tech",
    "QCOM": "Large-Cap-Tech", "CSCO": "Large-Cap-Tech", "DELL":  "Large-Cap-Tech",
    "BABA": "Large-Cap-Tech", "BIDU": "Large-Cap-Tech", "JD":    "Large-Cap-Tech",
    # 2x / 3x leveraged ETF proxies on mega-cap names
    "MSFU": "Large-Cap-Tech", "METU": "Large-Cap-Tech", "AMZU":  "Large-Cap-Tech",
    "TQQQ": "Large-Cap-Tech", "QQQ":  "Large-Cap-Tech", "XLK":   "Large-Cap-Tech",
    "SPY":  "Large-Cap-Tech", "SPXL": "Large-Cap-Tech",

    # ── Software ─────────────────────────────────────────────────────────────
    # SaaS, platforms, consumer-tech software, gaming, marketplaces
    "UBER": "Software", "PATH":  "Software", "SPOT":  "Software",
    "NFLX": "Software", "CRM":   "Software", "NOW":   "Software",
    "ADBE": "Software", "INTU":  "Software", "WDAY":  "Software",
    "CDNS": "Software", "SNPS":  "Software", "ANSS":  "Software",
    "DOCU": "Software", "SHOP":  "Software", "ABNB":  "Software",
    "DKNG": "Software", "RBLX":  "Software", "TTWO":  "Software",
    "EA":   "Software", "SE":    "Software", "ZM":    "Software",
    "LYFT": "Software", "DASH":  "Software", "GRAB":  "Software",
    "U":    "Software", "MELI":  "Software", "BILL":  "Software",

    # ── Fintech ──────────────────────────────────────────────────────────────
    # Payments, lending, exchanges, alt-asset management, banks
    "SOFI": "Fintech", "BN":    "Fintech", "PYPL":  "Fintech",
    "SQ":   "Fintech", "COIN":  "Fintech", "AFRM":  "Fintech",
    "V":    "Fintech", "MA":    "Fintech", "HOOD":  "Fintech",
    "NU":   "Fintech", "UPST":  "Fintech", "MSTR":  "Fintech",
    "SCHW": "Fintech", "IBKR":  "Fintech", "ICE":   "Fintech",
    "CME":  "Fintech", "CBOE":  "Fintech", "FICO":  "Fintech",
    "GS":   "Fintech", "JPM":   "Fintech", "MS":    "Fintech",
    "BAC":  "Fintech", "WFC":   "Fintech", "C":     "Fintech",
    "XLF":  "Fintech",

    # ── Energy-Transition ────────────────────────────────────────────────────
    # Storage, nuclear, uranium, solar, wind, grid, hydrogen, EVs (pure-play)
    "AMPX": "Energy-Transition", "TE":   "Energy-Transition", "LEU":  "Energy-Transition",
    "BE":   "Energy-Transition", "SHLS": "Energy-Transition", "NEXT": "Energy-Transition",
    "FLNC": "Energy-Transition", "XLU":  "Energy-Transition", "NEE":  "Energy-Transition",
    "ENPH": "Energy-Transition", "SEDG": "Energy-Transition", "FSLR": "Energy-Transition",
    "CEG":  "Energy-Transition", "VST":  "Energy-Transition", "CCJ":  "Energy-Transition",
    "SMR":  "Energy-Transition", "OKLO": "Energy-Transition", "UUUU": "Energy-Transition",
    "DNN":  "Energy-Transition", "PLUG": "Energy-Transition", "STEM": "Energy-Transition",
    "RIVN": "Energy-Transition", "LCID": "Energy-Transition", "CSIQ": "Energy-Transition",
    "RUN":  "Energy-Transition", "NOVA": "Energy-Transition", "ARRY": "Energy-Transition",
    "BEP":  "Energy-Transition", "NEP":  "Energy-Transition", "CLNE": "Energy-Transition",
    "XLE":  "Energy-Transition",

    # ── Defense-Space ────────────────────────────────────────────────────────
    # Aerospace, defense primes, satellites, eVTOL, dual-use
    "RKLB": "Defense-Space", "KRKNF": "Defense-Space", "ONDS":  "Defense-Space",
    "PL":   "Defense-Space", "USAR":  "Defense-Space", "LMT":   "Defense-Space",
    "RTX":  "Defense-Space", "NOC":   "Defense-Space", "GD":    "Defense-Space",
    "HII":  "Defense-Space", "KTOS":  "Defense-Space", "AVAV":  "Defense-Space",
    "ASTS": "Defense-Space", "LUNR":  "Defense-Space", "BWXT":  "Defense-Space",
    "LHX":  "Defense-Space", "HEI":   "Defense-Space", "TDG":   "Defense-Space",
    "IRDM": "Defense-Space", "SPIR":  "Defense-Space", "RDW":   "Defense-Space",
    "JOBY": "Defense-Space", "ACHR":  "Defense-Space", "MNTS":  "Defense-Space",
    "BA":   "Defense-Space", "AXON":  "Defense-Space",

    # ── Photonics ────────────────────────────────────────────────────────────
    # Optical interconnect, fiber lasers, lidar, photonic semiconductors
    "FOTO": "Photonics", "AAOI": "Photonics", "LITE":  "Photonics",
    "COHR": "Photonics", "IIVI": "Photonics", "LASR":  "Photonics",
    "IPGP": "Photonics", "CIEN": "Photonics", "VIAVI": "Photonics",
    "MKSI": "Photonics", "NOVT": "Photonics", "OLED":  "Photonics",

    # ── Cash ─────────────────────────────────────────────────────────────────
    # Short-duration T-bill ETFs and money-market proxies
    "SGOV": "Cash", "SHV": "Cash", "BIL": "Cash", "TBIL": "Cash",
    "USFR": "Cash", "VMFXX": "Cash",

    # ── Miscellaneous ────────────────────────────────────────────────────────
    # Consumer brands, speculative, meme, does not fit above
    "BROS": "Miscellaneous", "ONON": "Miscellaneous", "PURR":  "Miscellaneous",
    "AMC":  "Miscellaneous", "GME":  "Miscellaneous", "TLRY":  "Miscellaneous",
    "F":    "Miscellaneous", "GM":   "Miscellaneous", "NIO":   "Miscellaneous",
    "XPEV": "Miscellaneous", "LI":   "Miscellaneous", "SIRI":  "Miscellaneous",
}


def classify_theme(underlying: str) -> str:
    """Return the theme for a given underlying ticker, defaulting to Miscellaneous."""
    return THEME_MAP.get(underlying.upper(), "Miscellaneous")


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
        asset   = p.get("asset_class") or ("OPT" if any(w in desc for w in ("CALL", "PUT")) else "STK")
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
    STOCK_STRATEGIES = {"Thematic", "2x-ETF", "cash", "WheelASG"}
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
        if consumed is not None:
            consumed.add(underlying.upper())
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

    Split stock handling: when a _STK position (WheelSC assigned lot) exists for the
    same underlying as a 2x-ETF/Thematic position, IBKR reports a single combined
    qty. We split it: _STK gets its DB qty (fixed — never overwritten from IBKR),
    the base ticker gets the residual. MV is allocated proportionally.
    """
    updated  = 0
    missed   = 0
    consumed: set = set()

    # Pre-scan: build split map for underlyings that have a _STK position
    # {UNDERLYING_UPPER: {"fixed_qty": int, "cost_basis": float, "assign_px": float}}
    stk_splits: dict[str, dict] = {}
    for pos in positions_db:
        if pos["symbol"].upper().endswith("_STK"):
            und = pos["underlying"].upper()
            assign_px = float(pos.get("assignment_price") or 0)
            stk_splits[und] = {
                "fixed_qty":  abs(int(pos["qty"] or 0)),
                "cost_basis": float(pos["cost_basis"] or 0),
                "assign_px":  assign_px,
            }

    for pos in positions_db:
        pid        = pos["id"]
        symbol     = pos["symbol"]
        strategy   = pos["strategy"]
        underlying = pos["underlying"]
        cost_basis = float(pos["cost_basis"] or 0)
        db_qty     = int(pos["qty"] or 0)
        assign_px  = float(pos.get("assignment_price") or 0)
        sym_upper  = symbol.upper()
        und_upper  = underlying.upper()

        # ── _STK leg: fixed qty, proportional MV, cost from assignment_price ─
        if sym_upper.endswith("_STK") and und_upper in stk_splits:
            ibkr_entry = stocks.get(underlying)
            if ibkr_entry is None:
                missed += 1
                continue
            ibkr_total = abs(ibkr_entry["qty"])
            ibkr_mv    = ibkr_entry["mv"]
            fixed_qty  = abs(db_qty)  # locked; never pull from IBKR
            cv         = round(ibkr_mv * fixed_qty / ibkr_total, 2) if ibkr_total else 0
            qty        = fixed_qty
            # Cost basis: assignment_price × shares if set, else preserve DB value
            if assign_px > 0:
                cost_basis = round(assign_px * fixed_qty, 2)
            consumed.add(und_upper)

        # ── Base stock with a _STK split: residual shares only ───────────────
        elif und_upper in stk_splits and not sym_upper.endswith("_STK"):
            ibkr_entry = stocks.get(underlying)
            if ibkr_entry is None:
                missed += 1
                continue
            ibkr_total = abs(ibkr_entry["qty"])
            ibkr_mv    = ibkr_entry["mv"]
            stk_qty    = stk_splits[und_upper]["fixed_qty"]
            qty        = ibkr_total - stk_qty
            cv         = round(ibkr_mv * qty / ibkr_total, 2) if ibkr_total else 0
            consumed.add(und_upper)

        # ── Normal path ───────────────────────────────────────────────────────
        else:
            cv, ibkr_qty = resolve_current_value(
                symbol, strategy, underlying, stocks, opts, opts_day, fx_gbp, consumed
            )
            if cv is None:
                missed += 1
                continue
            qty = ibkr_qty if ibkr_qty is not None else abs(db_qty)
            if db_qty < 0:
                qty = -qty

        # ── Gain % and NAV % ─────────────────────────────────────────────────
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
    stocks: dict,
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
        desc_ac = p["contract_description"]
        asset_ac = p.get("asset_class") or ("OPT" if any(w in desc_ac for w in ("CALL", "PUT")) else "STK")
        if asset_ac != "OPT":
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

    # ── Pass 3: unmatched long single calls → LEAP ───────────────────────────
    for opt in unmatched:
        if opt["key_yr"] in pair_consumed:
            continue
        if opt["ibkr_qty"] <= 0:
            continue  # only long options
        if opt["cp"] != "CALL":
            continue  # skip long puts (protective puts; not LEAPs)
        abs_qty = abs(opt["ibkr_qty"])
        avg     = opt["avg_price"]
        mv      = opt["mv"]
        symbol  = f"{opt['und']}_{opt['mon3']}{opt['year2']}_{_fmt(opt['strike'])}C"
        cost_basis    = round(avg * abs_qty * 100, 2) if avg > 0 else round(abs(mv), 2)
        current_value = round(abs(mv), 2)
        to_create.append({
            "symbol": symbol, "underlying": opt["und"], "strategy": "LEAP",
            "abs_qty": abs_qty, "cost_basis": cost_basis, "current_value": current_value,
            "is_short": False,
        })

    # ── Pass 4: unmatched IBKR stocks → Thematic ─────────────────────────────
    SKIP_TICKERS = {"SGOV"}
    for ticker, entry in stocks.items():
        t = ticker.upper()
        if t in SKIP_TICKERS:
            continue
        if t in consumed:
            continue
        abs_qty = abs(entry["qty"])
        mv      = entry["mv"]
        avg_price = 0.0
        for p in positions_raw:
            asset = p.get("asset_class") or ("OPT" if any(w in p["contract_description"] for w in ("CALL", "PUT")) else "STK")
            if asset == "STK" and p["contract_description"].split()[0].upper() == t:
                avg_price = float(p.get("average_price", 0) or 0)
                break
        cost_basis    = round(avg_price * abs_qty, 2) if avg_price > 0 else round(abs(mv), 2)
        current_value = round(abs(mv), 2)
        to_create.append({
            "symbol": t, "underlying": t, "strategy": "Thematic",
            "abs_qty": abs_qty, "cost_basis": cost_basis, "current_value": current_value,
            "is_short": False,
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

        theme = classify_theme(underlying)
        cur.execute("""
            INSERT INTO positions
                (owner_id, account_id, symbol, underlying, strategy, theme,
                 opened_date, qty_at_open, cost_basis_at_open, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ibkr-auto')
            ON CONFLICT (account_id, symbol) WHERE closed_date IS NULL DO NOTHING
            RETURNING id
        """, (owner_id, account_id, symbol, underlying, strategy, theme,
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

        msg = f"auto-created: {symbol} | strategy={strategy} | theme={theme} | qty={abs_qty} | cost_basis=${cost_basis:.2f}"
        print(f"  {msg}")
        rlog.ok(msg)
        created += 1

    return created


# ── Main ─────────────────────────────────────────────────────────────────────

def auto_close_missing_positions(
    cur,
    positions_db: list[dict],
    stocks: dict,
    opts: dict,
    opts_day: dict,
    today: str,
    account_id: int = 1,
) -> int:
    """
    Close any open position that has no matching entry in the current IBKR data.

    Covers all strategies — Wheel options/stock, SWING, LDS, LEAP, Thematic,
    2x-ETF.  Only 'cash' is exempt (SGOV and cash never expire).

    Stock positions: check if underlying ticker is still present in IBKR stocks.
    Option positions: parse the symbol and check opts (year-keyed) and opts_day
    (month+day+year-keyed).  Short-dated WheelSP/SC symbols encode month+day
    (e.g. JUL17); we try plausible year suffixes so they resolve correctly while
    still catching truly expired contracts.
    """
    STOCK_STRATEGIES = {"WheelASG", "Thematic", "2x-ETF"}
    SKIP_STRATEGIES  = {"cash"}

    # opts_day keys are already year-agnostic: (und, mon3, day2, strike, cp)
    # — no year component — so we check opts_day directly for short-dated symbols.

    current_yr2 = date.today().year % 100
    year_candidates = [str(y) for y in range(current_yr2 - 1, current_yr2 + 6)]

    closed = 0
    stocks_upper = {k.upper() for k in stocks}

    for pos in positions_db:
        if pos["strategy"] in SKIP_STRATEGIES:
            continue

        symbol     = pos["symbol"]
        strategy   = pos["strategy"]
        underlying = pos["underlying"]
        sym_upper  = symbol.upper()
        und_upper  = underlying.upper()

        still_open = False

        if strategy in STOCK_STRATEGIES or sym_upper.endswith("_STK"):
            still_open = und_upper in stocks_upper

        else:
            parts = sym_upper.split("_")
            if len(parts) >= 3:
                monyy = parts[1]          # e.g. "JUL17" or "DEC27"
                mon3  = monyy[:3].upper() # "JUL"
                tail  = monyy[3:]         # "17" (day) or "27" (year)
                legs  = re.findall(r"([\d.]+)([CP])", parts[2])

                for strike, cp_char in legs:
                    cp = "CALL" if cp_char == "C" else "PUT"

                    # Direct year-keyed lookup (works for spreads / LEAPs)
                    if (und_upper, tail, strike, cp) in opts:
                        still_open = True
                        break

                    # Short-dated symbol: tail is the day, not the year.
                    # Try all plausible years in opts.
                    for yr in year_candidates:
                        if (und_upper, yr, strike, cp) in opts:
                            still_open = True
                            break

                    if still_open:
                        break

                    # opts_day lookup: (und, mon3, day2, strike, cp) — no year
                    if (und_upper, mon3, tail, strike, cp) in opts_day:
                        still_open = True
                        break

        if not still_open:
            cur.execute("""
                UPDATE positions SET closed_date = %s
                WHERE id = %s AND closed_date IS NULL
            """, (today, pos["id"]))
            if cur.rowcount:
                msg = f"auto-closed: {symbol} (not in IBKR)"
                print(f"  {msg}")
                rlog.ok(msg)
                closed += 1

    return closed


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

            # Load ALL open positions with their most recent snapshot.
            # Using LATERAL so positions with no current-date snapshot (e.g. old
            # expired WheelSPs never cleaned up) are still included — both for the
            # upsert attempt AND for auto_close_missing_positions.
            cur.execute("""
                SELECT p.id, p.symbol, p.underlying, p.strategy,
                       p.assignment_price,
                       COALESCE(ps.cost_basis, 0) AS cost_basis,
                       COALESCE(ps.qty, 0)        AS qty
                FROM positions p
                JOIN accounts a ON a.id = p.account_id
                LEFT JOIN LATERAL (
                    SELECT cost_basis, qty
                    FROM position_snapshots
                    WHERE position_id = p.id
                    ORDER BY snapshot_date DESC
                    LIMIT 1
                ) ps ON true
                WHERE a.ibkr_account_id = 'U15760849'
                  AND p.closed_date IS NULL
                ORDER BY p.symbol
            """)
            positions_db = list(cur.fetchall())

            updated, missed, consumed = upsert_position_snapshots(
                cur, positions_db, stocks, opts, opts_day, nav, today, fx_gbp
            )

            created = auto_create_missing_options(
                cur, positions_raw, consumed, nav, today, stocks
            )

            auto_closed = auto_close_missing_positions(
                cur, positions_db, stocks, opts, opts_day, today
            )

        msg = f"positions: {updated} updated, {created} auto-created, {auto_closed} auto-closed, {missed} no IBKR match"
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
