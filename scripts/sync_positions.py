#!/usr/bin/env python3
"""
Deterministic positions updater.

Reads ibkr_positions.json + account_state.json from ROUTINE_DIR,
matches against open_positions.csv, rewrites the CSV with today's
current_value / gain_pct / pct_nav.

Called by ibkr_bridge.py after claude -p writes the raw IBKR data.
Can also be run standalone for debugging.
"""

import csv
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

ROUTINE_DIR = Path.home() / "workspace" / "trading-routine"


# ── IBKR data parsing ────────────────────────────────────────────────────────

def _extract_ticker(contract_description: str) -> str:
    """Extract the underlying ticker from an IBKR contract description."""
    return contract_description.split()[0]


def index_ibkr_positions(positions: list[dict]) -> tuple[dict, dict, dict]:
    """
    Build lookup dicts from raw IBKR position list.

    stocks:    underlying_ticker → market_value_usd
    opts:      (underlying, year2, strike_str, "CALL"|"PUT") → market_value_usd
    opts_day:  (underlying, mon3_upper, day2, strike_str, "CALL"|"PUT") → market_value_usd
               e.g. ONDS Jul02'26 → key ("ONDS", "JUL", "02", "10.5", "CALL")
    """
    stocks:   dict[str, float] = {}
    opts:     dict[tuple, float] = {}
    opts_day: dict[tuple, float] = {}

    # Format: "UNDERLYING MonDD'YY STRIKE CALL/PUT @EXCHANGE"
    OPT_RE = re.compile(r"(\w+)\s+([A-Za-z]{3})(\d{2})'(\d{2})\s+([\d.]+)\s+(CALL|PUT)")

    for p in positions:
        desc  = p["contract_description"]
        asset = p["asset_class"]
        mv    = float(p["market_value"])

        if asset == "STK":
            ticker = _extract_ticker(desc)
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
                # Year-based key (e.g. DEC27 symbols)
                opts[(und, year2, strike, cp)] = opts.get((und, year2, strike, cp), 0.0) + mv
                # Day-based key (e.g. JUL02 symbols for weeklies)
                opts_day[(und, mon3, day2, strike, cp)] = opts_day.get((und, mon3, day2, strike, cp), 0.0) + mv

    return stocks, opts, opts_day


# ── CSV symbol parsing ───────────────────────────────────────────────────────

def _parse_legs(legs_str: str) -> list[tuple[str, str]]:
    """
    Parse the legs portion of a CSV symbol (e.g. "170C270C" → [(170, C), (270, C)]).
    Returns list of (strike_str, "CALL"|"PUT").
    """
    matches = re.findall(r"([\d.]+)([CP])", legs_str)
    return [(s, "CALL" if t == "C" else "PUT") for s, t in matches]


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
    Return the live current_value for a CSV row, or None if no IBKR match.

    Convention (matches existing CSV):
      - Long positions:  current_value = market_value (positive)
      - Short options:   current_value = abs(market_value) (the buyback cost, positive)
      - Spreads:         current_value = sum of both legs (net, may be negative if inverted)
    """
    STOCK_STRATEGIES = {"Thematic", "2x-ETF", "cash"}

    sym = symbol.upper()
    parts = sym.split("_")

    # ── Stocks ────────────────────────────────────────────────────────────────
    is_stock = (
        strategy in STOCK_STRATEGIES
        or len(parts) < 2
        or (len(parts) == 2 and parts[-1] == "STK")
        or (len(parts) >= 2 and not re.search(r"\d", parts[-1]))
    )

    if is_stock:
        mv = stocks.get(underlying)
        if mv is None:
            # Try with exchange suffix stripped (e.g. IQE stored as "IQE" not "IQE @LSE")
            return None
        # IQE is GBP — convert (stocks dict stores raw market_value in native currency)
        # We detect GBP stocks by checking if IBKR ticker appears with @LSE
        return mv * fx_gbp if underlying == "IQE" else mv

    # ── Options ───────────────────────────────────────────────────────────────
    if len(parts) < 3:
        return None

    und    = parts[0]
    monyy  = parts[1]           # e.g. "DEC27", "JAN28", "JUN26"
    year2  = monyy[3:]          # "27", "28", "26"
    legs   = _parse_legs(parts[2])

    if not legs:
        return None

    if len(legs) == 1:
        # Single-leg option (LEAP, WheelSP, WheelSC, SWING single)
        strike, cp = legs[0]
        mv = opts.get((und, year2, strike, cp))
        if mv is None:
            # Try day-based key for weeklies like ONDS_JUL02_10.5C
            # year2 here could be a 2-digit day (e.g. "02" from JUL02)
            mon3 = monyy[:3].upper()
            day2 = year2  # reuse as day when it looks like a day (01-31)
            mv = opts_day.get((und, mon3, day2, strike, cp))
        if mv is None:
            return None
        # For short options (market_value negative) return abs so CSV stays positive
        return abs(mv) if mv < 0 else mv

    else:
        # Spread (LDS, CDS, SWING): sum all legs
        total = 0.0
        matched = 0
        for strike, cp in legs:
            key = (und, year2, strike, cp)
            if key in opts:
                total += opts[key]
                matched += 1
        return total if matched > 0 else None


# ── CSV update ───────────────────────────────────────────────────────────────

def update_positions_csv(
    csv_path: Path,
    positions: list[dict],
    nav: float,
    fx_gbp: float = 1.32,
    today: str | None = None,
) -> str:
    """
    Return updated CSV string with today's current_value / gain_pct / pct_nav.
    All other columns are preserved unchanged.
    """
    stocks, opts, opts_day = index_ibkr_positions(positions)
    today = today or date.today().isoformat()

    text    = csv_path.read_text()
    reader  = csv.DictReader(io.StringIO(text))
    fields  = reader.fieldnames or []

    out_rows = []
    matched  = 0
    skipped  = 0

    for row in reader:
        symbol     = row.get("symbol", "")
        strategy   = row.get("strategy", "")
        underlying = row.get("underlying", "")
        qty_str    = row.get("qty", "0")
        cost_str   = row.get("cost_basis", "0")

        cv = resolve_current_value(symbol, strategy, underlying, stocks, opts, opts_day, fx_gbp)

        if cv is not None:
            try:
                cost_basis = float(cost_str)
                qty        = float(qty_str)

                if qty < 0:
                    # Short option: gain = (premium_received - buyback_cost) / premium_received
                    gain_pct = round((cost_basis - cv) / abs(cost_basis) * 100, 1) if cost_basis else 0.0
                else:
                    gain_pct = round((cv - cost_basis) / abs(cost_basis) * 100, 1) if cost_basis else 0.0

                pct_nav = round(cv / nav * 100, 2) if nav else 0.0

                row["date"]          = today
                row["current_value"] = round(cv, 2)
                row["gain_pct"]      = gain_pct
                row["pct_nav"]       = pct_nav
                matched += 1
            except (ValueError, ZeroDivisionError):
                skipped += 1
        else:
            skipped += 1  # no IBKR match — leave row unchanged

        out_rows.append(row)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out_rows)

    print(f"  positions: {matched} updated, {skipped} unchanged (no IBKR match)")
    return out.getvalue()


# ── Main ─────────────────────────────────────────────────────────────────────

def run(routine_dir: Path = ROUTINE_DIR) -> bool:
    state_path  = routine_dir / "account_state.json"
    ibkr_path   = routine_dir / "ibkr_positions.json"
    csv_path    = routine_dir / "open_positions.csv"

    if not state_path.exists():
        print("ERROR: account_state.json not found", file=sys.stderr)
        return False
    if not ibkr_path.exists():
        print("ERROR: ibkr_positions.json not found — run bridge first", file=sys.stderr)
        return False
    if not csv_path.exists():
        print("ERROR: open_positions.csv not found", file=sys.stderr)
        return False

    state     = json.loads(state_path.read_text())
    nav       = float(state["nav"])
    today     = state.get("date") or date.today().isoformat()
    positions = json.loads(ibkr_path.read_text())["positions"]

    # IQE exchange rate: look up from state if stored, else default
    fx_gbp = float(state.get("fx_gbp", 1.32))

    updated_csv = update_positions_csv(csv_path, positions, nav, fx_gbp, today)
    csv_path.write_text(updated_csv)
    print(f"  open_positions.csv written ({today})")
    return True


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
