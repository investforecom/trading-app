"""
Load the IBKR Flex Query CSV → closed_trades (and optionally seeds positions).

The Flex CSV contains multiple sections, each with its own header row.
We detect section boundaries by looking for rows that start with a known header token.

Sections we care about:
  - Trades (EXECUTION rows, Open/CloseIndicator = C) → closed_trades
  - Option Exercises, Assignments and Expirations       → closed_trades
  - Open Positions (SUMMARY rows)                       → seed positions (optional)

The Trades section header starts with "Symbol","UnderlyingSymbol",...
The Exercises section header starts with "ClientAccountID",...,"Transaction Type",...
The Open Positions section header starts with "ClientAccountID",...,"MarkPrice",...
"""
import csv
import io
from collections import defaultdict
from pathlib import Path
from typing import Optional

from db import transaction
from util import parse_date_flex, parse_decimal, safe_strategy, derive_underlying
from positions_registry import PositionsRegistry


# ---------------------------------------------------------------------------
# Section detection helpers
# ---------------------------------------------------------------------------

def _is_trades_header(row: list[str]) -> bool:
    return (
        len(row) > 5
        and row[0] == "Symbol"
        and row[1] == "UnderlyingSymbol"
        and row[6] == "Put/Call"
    )


def _is_exercises_header(row: list[str]) -> bool:
    return (
        len(row) > 28
        and row[0] == "ClientAccountID"
        and "Transaction Type" in row
    )


def _is_open_positions_header(row: list[str]) -> bool:
    return (
        len(row) > 30
        and row[0] == "ClientAccountID"
        and "MarkPrice" in row
        and "Transaction Type" not in row
    )


# ---------------------------------------------------------------------------
# Structure string builder from Flex fields
# ---------------------------------------------------------------------------

def _build_structure(asset_class: str, put_call: str, strike: str, expiry: str) -> Optional[str]:
    if asset_class == "STK":
        return "shares"
    if not strike or not expiry:
        return None
    pc = put_call.strip().upper()
    s = strike.rstrip("0").rstrip(".")
    exp_str = expiry.strip()
    if len(exp_str) == 8:
        exp_str = f"{exp_str[:4]}-{exp_str[4:6]}-{exp_str[6:]}"
    return f"{s}{pc} exp {exp_str}"


def _derive_strategy_flex(asset_class: str, put_call: str, sub_category: str) -> str:
    """Best-effort strategy from Flex fields. CSV closed_trades.csv is the authority."""
    if asset_class == "STK":
        return "Thematic"
    pc = put_call.strip().upper()
    if pc == "P":
        return "WheelSP"
    if pc == "C":
        return "LEAP"
    return "other"


# ---------------------------------------------------------------------------
# Trades section loader (EXECUTION close rows)
# ---------------------------------------------------------------------------

def _load_trades_section(
    rows: list[list[str]],
    header: list[str],
    cur,
    owner_id: int,
    account_id: int,
    registry: PositionsRegistry,
    seq_counter: dict,
) -> tuple[int, int]:
    """Returns (inserted, skipped)."""
    col = {name: i for i, name in enumerate(header)}
    inserted = skipped = 0

    for row in rows:
        if len(row) != len(header):
            skipped += 1
            continue

        level_of_detail = row[col["LevelOfDetail"]]
        if level_of_detail != "EXECUTION":
            continue

        open_close = row[col["Open/CloseIndicator"]]
        if open_close != "C":
            continue

        ibkr_exec_id = row[col["IBExecID"]].strip() or None
        if not ibkr_exec_id:
            skipped += 1
            continue

        symbol           = row[col["Symbol"]].strip()
        underlying       = row[col["UnderlyingSymbol"]].strip() or derive_underlying(symbol)
        asset_class      = row[col["AssetClass"]].strip()
        sub_category     = row[col.get("SubCategory", -1)].strip() if "SubCategory" in col else ""
        put_call         = row[col["Put/Call"]].strip()
        strike           = row[col["Strike"]].strip()
        expiry           = row[col["Expiry"]].strip()
        trade_date       = parse_date_flex(row[col["TradeDate"]])
        open_datetime    = parse_date_flex(row[col["OpenDateTime"]])
        qty_raw          = row[col["Quantity"]].strip()
        cost_basis_raw   = row[col["CostBasis"]].strip()
        net_cash_raw     = row[col["NetCash"]].strip()
        realized_pnl_raw = row[col["FifoPnlRealized"]].strip()

        if not trade_date or not symbol:
            skipped += 1
            continue

        qty          = abs(int(float(qty_raw))) if qty_raw else 0
        cost_basis   = parse_decimal(cost_basis_raw)
        exit_value   = parse_decimal(net_cash_raw)
        realized_pnl = parse_decimal(realized_pnl_raw)
        structure    = _build_structure(asset_class, put_call, strike, expiry)
        strategy     = _derive_strategy_flex(asset_class, put_call, sub_category)

        if realized_pnl is None:
            skipped += 1
            continue

        gain_pct: Optional[float] = None
        if cost_basis and cost_basis != 0:
            gain_pct = round((realized_pnl / abs(cost_basis)) * 100, 4)

        hold_days: Optional[int] = None
        if open_datetime and trade_date:
            hold_days = (trade_date - open_datetime).days

        position_id = registry.lookup_any(symbol)

        # Close the open position if tracked
        if registry.lookup_open(symbol):
            registry.close(symbol, trade_date)

        group_key = (trade_date, symbol, strategy)
        seq_counter[group_key] += 1
        row_seq = seq_counter[group_key]

        cur.execute(
            """
            INSERT INTO closed_trades (
                owner_id, account_id, position_id,
                close_date, open_date, symbol, underlying,
                strategy, structure, qty,
                cost_basis, exit_value, realized_pnl, gain_pct,
                hold_days, ibkr_exec_id, row_seq, source
            ) VALUES (
                %(owner_id)s, %(account_id)s, %(position_id)s,
                %(close_date)s, %(open_date)s, %(symbol)s, %(underlying)s,
                %(strategy)s, %(structure)s, %(qty)s,
                %(cost_basis)s, %(exit_value)s, %(realized_pnl)s, %(gain_pct)s,
                %(hold_days)s, %(ibkr_exec_id)s, %(row_seq)s, 'ibkr_flex'
            )
            ON CONFLICT (ibkr_exec_id) WHERE ibkr_exec_id IS NOT NULL DO NOTHING
            """,
            dict(
                owner_id=owner_id,
                account_id=account_id,
                position_id=position_id,
                close_date=trade_date,
                open_date=open_datetime,
                symbol=symbol,
                underlying=underlying,
                strategy=strategy,
                structure=structure,
                qty=qty,
                cost_basis=cost_basis,
                exit_value=exit_value,
                realized_pnl=realized_pnl,
                gain_pct=gain_pct,
                hold_days=hold_days,
                ibkr_exec_id=ibkr_exec_id,
                row_seq=row_seq,
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    return inserted, skipped


# ---------------------------------------------------------------------------
# Exercises / Assignments / Expirations section loader
# ---------------------------------------------------------------------------

def _load_exercises_section(
    rows: list[list[str]],
    header: list[str],
    cur,
    owner_id: int,
    account_id: int,
    registry: PositionsRegistry,
    seq_counter: dict,
) -> tuple[int, int]:
    col = {name: i for i, name in enumerate(header)}
    inserted = skipped = 0

    for row in rows:
        if len(row) != len(header):
            skipped += 1
            continue

        txn_type = row[col["Transaction Type"]].strip()
        # Assignment/Expiration events on the OPTION leg only
        # (the paired STK row is handled separately; we skip it to avoid double-counting)
        asset_class = row[col["AssetClass"]].strip() if "AssetClass" in col else ""
        if asset_class == "STK":
            skipped += 1
            continue

        trade_date   = parse_date_flex(row[col["Date"]].strip())
        symbol       = row[col["Symbol"]].strip()
        underlying   = row[col["UnderlyingSymbol"]].strip() or derive_underlying(symbol)
        put_call     = row[col["Put/Call"]].strip()
        strike       = row[col["Strike"]].strip()
        expiry       = row[col["Expiry"]].strip()
        qty_raw      = row[col["Quantity"]].strip()
        basis_raw    = row[col["Basis"]].strip()
        realized_raw = row[col["RealizedPnl"]].strip()
        trade_id     = row[col["TradeID"]].strip()

        if not trade_date or not symbol:
            skipped += 1
            continue

        qty          = abs(int(float(qty_raw))) if qty_raw else 0
        cost_basis   = parse_decimal(basis_raw)
        realized_pnl = parse_decimal(realized_raw) or 0.0

        # For expirations: proceeds = 0; for assignments: proceeds = strike × qty × multiplier
        exit_value   = 0.0
        if txn_type == "Assignment":
            try:
                exit_value = float(strike) * qty * 100
            except (ValueError, TypeError):
                exit_value = 0.0

        gain_pct: Optional[float] = None
        if cost_basis and cost_basis != 0:
            gain_pct = round((realized_pnl / abs(cost_basis)) * 100, 4)

        structure = _build_structure(asset_class, put_call, strike, expiry)
        strategy  = "WheelSP" if put_call.upper() == "P" else "WheelSC"

        exit_reason = txn_type  # "Expiration", "Assignment", "Exercise"

        # Use TradeID as the exec-ID equivalent for exercises (no IBExecID in this section)
        ibkr_exec_id = f"EX-{trade_id}" if trade_id else None

        position_id = registry.lookup_any(symbol)
        if registry.lookup_open(symbol):
            registry.close(symbol, trade_date)

        group_key = (trade_date, symbol, strategy)
        seq_counter[group_key] += 1
        row_seq = seq_counter[group_key]

        cur.execute(
            """
            INSERT INTO closed_trades (
                owner_id, account_id, position_id,
                close_date, symbol, underlying,
                strategy, structure, qty,
                cost_basis, exit_value, realized_pnl, gain_pct,
                exit_reason, ibkr_exec_id, row_seq, source
            ) VALUES (
                %(owner_id)s, %(account_id)s, %(position_id)s,
                %(close_date)s, %(symbol)s, %(underlying)s,
                %(strategy)s, %(structure)s, %(qty)s,
                %(cost_basis)s, %(exit_value)s, %(realized_pnl)s, %(gain_pct)s,
                %(exit_reason)s, %(ibkr_exec_id)s, %(row_seq)s, 'ibkr_flex'
            )
            ON CONFLICT (ibkr_exec_id) WHERE ibkr_exec_id IS NOT NULL DO NOTHING
            """,
            dict(
                owner_id=owner_id,
                account_id=account_id,
                position_id=position_id,
                close_date=trade_date,
                symbol=symbol,
                underlying=underlying,
                strategy=strategy,
                structure=structure,
                qty=qty,
                cost_basis=cost_basis,
                exit_value=exit_value,
                realized_pnl=realized_pnl,
                gain_pct=gain_pct,
                exit_reason=exit_reason,
                ibkr_exec_id=ibkr_exec_id,
                row_seq=row_seq,
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    return inserted, skipped


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def load(flex_path: Path, account_id: int, owner_id: int):
    """
    Parse the multi-section Flex CSV, then load in one transaction.
    Sections are split by detecting header rows mid-file.
    """
    # Split the file into labelled sections
    trades_header: Optional[list[str]]    = None
    trades_rows:   list[list[str]]        = []
    exercises_header: Optional[list[str]] = None
    exercises_rows:   list[list[str]]     = []

    with open(flex_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        current = None  # "trades" | "exercises" | None

        for raw_row in reader:
            row = [c.strip() for c in raw_row]

            if _is_trades_header(row):
                trades_header = row
                current = "trades"
                continue
            if _is_exercises_header(row):
                exercises_header = row
                current = "exercises"
                continue
            if _is_open_positions_header(row):
                current = None  # we don't load open positions from Flex
                continue

            if current == "trades":
                trades_rows.append(row)
            elif current == "exercises":
                exercises_rows.append(row)

    with transaction() as cur:
        registry = PositionsRegistry(cur, owner_id, account_id)
        seq_counter: dict[tuple, int] = defaultdict(int)

        t_ins, t_skip = (0, 0)
        if trades_header:
            t_ins, t_skip = _load_trades_section(
                trades_rows, trades_header, cur,
                owner_id, account_id, registry, seq_counter,
            )

        e_ins, e_skip = (0, 0)
        if exercises_header:
            e_ins, e_skip = _load_exercises_section(
                exercises_rows, exercises_header, cur,
                owner_id, account_id, registry, seq_counter,
            )

    print(
        f"flex trades:    {t_ins} inserted, {t_skip} skipped\n"
        f"flex exercises: {e_ins} inserted, {e_skip} skipped"
    )
