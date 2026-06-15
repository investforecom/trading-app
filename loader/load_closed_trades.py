"""
Load closed_trades.csv → closed_trades table.

The CSV is append-only and user-curated. Idempotency key:
  (account_id, close_date, symbol, strategy, row_seq)
row_seq handles the rare case of multiple closes for the same symbol/strategy on one day.
"""
import csv
from collections import defaultdict
from pathlib import Path

from db import transaction
from util import (
    parse_decimal, parse_int, parse_date_csv,
    derive_underlying, safe_strategy, parse_hold_days,
)
from positions_registry import PositionsRegistry


def load(csv_path: Path, account_id: int, owner_id: int):
    with transaction() as cur:
        registry = PositionsRegistry(cur, owner_id, account_id)
        # Track row_seq within (close_date, symbol, strategy) groups
        seq_counter: dict[tuple, int] = defaultdict(int)
        inserted = 0
        skipped = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                close_date   = parse_date_csv(row["close_date"])
                open_date    = parse_date_csv(row["open_date"])
                symbol       = row["symbol"].strip()
                strategy     = safe_strategy(row["strategy"])
                structure    = row["structure"].strip() or None
                qty          = abs(parse_int(row["qty"]) or 0)
                cost_basis   = parse_decimal(row["cost_basis"])
                exit_value   = parse_decimal(row["exit_value"])
                realized_pnl = parse_decimal(row["realized_pnl"])
                gain_pct     = parse_decimal(row["gain_pct"])
                hold_days    = parse_hold_days(row["hold_days"])
                exit_reason  = row["exit_reason"].strip() or None

                if not close_date or not symbol or realized_pnl is None:
                    skipped += 1
                    continue

                underlying = derive_underlying(symbol)

                # Link to the positions table (best-effort: match by symbol, prefer closed)
                position_id = registry.lookup_any(symbol)

                # Close the open position episode if it exists and isn't already closed
                if close_date and registry.lookup_open(symbol):
                    registry.close(symbol, close_date)

                group_key = (close_date, symbol, strategy)
                seq_counter[group_key] += 1
                row_seq = seq_counter[group_key]

                cur.execute(
                    """
                    INSERT INTO closed_trades (
                        owner_id, account_id, position_id,
                        close_date, open_date, symbol, underlying,
                        strategy, structure, qty,
                        cost_basis, exit_value, realized_pnl, gain_pct,
                        hold_days, exit_reason, row_seq, source
                    ) VALUES (
                        %(owner_id)s, %(account_id)s, %(position_id)s,
                        %(close_date)s, %(open_date)s, %(symbol)s, %(underlying)s,
                        %(strategy)s, %(structure)s, %(qty)s,
                        %(cost_basis)s, %(exit_value)s, %(realized_pnl)s, %(gain_pct)s,
                        %(hold_days)s, %(exit_reason)s, %(row_seq)s, 'csv'
                    )
                    ON CONFLICT (account_id, close_date, symbol, strategy, row_seq)
                    DO NOTHING
                    """,
                    dict(
                        owner_id=owner_id,
                        account_id=account_id,
                        position_id=position_id,
                        close_date=close_date,
                        open_date=open_date,
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
                        exit_reason=exit_reason,
                        row_seq=row_seq,
                    ),
                )
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1

        print(f"closed_trades (csv): {inserted} inserted, {skipped} skipped")
