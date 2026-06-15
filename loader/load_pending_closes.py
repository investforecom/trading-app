"""
Load pending_closes.csv → pending_closes table + auto-promote to closed_trades.

No manual confirmation step. Every detected close is immediately written to both tables.
pending_closes serves as an audit log only.
"""
import csv
from collections import defaultdict
from pathlib import Path

from db import transaction
from util import (
    parse_decimal, parse_int, parse_date_csv,
    derive_underlying, safe_strategy,
)
from positions_registry import PositionsRegistry


def load(csv_path: Path, account_id: int, owner_id: int):
    with transaction() as cur:
        registry = PositionsRegistry(cur, owner_id, account_id)
        seq_counter: dict[tuple, int] = defaultdict(int)
        inserted_pending = 0
        inserted_trades = 0
        skipped = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                detected_date    = parse_date_csv(row["detected_date"])
                symbol           = row["symbol"].strip()
                strategy         = safe_strategy(row["strategy"])
                structure        = row["structure"].strip() or None
                qty              = abs(parse_int(row["qty"]) or 0)
                cost_basis       = parse_decimal(row["cost_basis"])
                last_value       = parse_decimal(row["last_value"])
                est_realized_pnl = parse_decimal(row["est_realized_pnl"])
                likely_reason    = row["likely_reason"].strip() or None

                if not detected_date or not symbol:
                    skipped += 1
                    continue

                underlying = derive_underlying(symbol)
                position_id = registry.lookup_any(symbol)

                # Insert into pending_closes log
                cur.execute(
                    """
                    INSERT INTO pending_closes (
                        owner_id, account_id, position_id,
                        detected_date, symbol, underlying,
                        strategy, structure, qty,
                        cost_basis, last_value, est_realized_pnl,
                        likely_reason, status, resolved_date
                    ) VALUES (
                        %(owner_id)s, %(account_id)s, %(position_id)s,
                        %(detected_date)s, %(symbol)s, %(underlying)s,
                        %(strategy)s, %(structure)s, %(qty)s,
                        %(cost_basis)s, %(last_value)s, %(est_realized_pnl)s,
                        %(likely_reason)s, 'auto_confirmed', %(detected_date)s
                    )
                    ON CONFLICT (account_id, detected_date, symbol) DO NOTHING
                    """,
                    dict(
                        owner_id=owner_id,
                        account_id=account_id,
                        position_id=position_id,
                        detected_date=detected_date,
                        symbol=symbol,
                        underlying=underlying,
                        strategy=strategy,
                        structure=structure,
                        qty=qty,
                        cost_basis=cost_basis,
                        last_value=last_value,
                        est_realized_pnl=est_realized_pnl,
                        likely_reason=likely_reason,
                    ),
                )
                if cur.rowcount:
                    inserted_pending += 1
                else:
                    skipped += 1
                    continue  # already processed; skip closed_trades insert too

                # Auto-promote to closed_trades using estimated values
                if registry.lookup_open(symbol):
                    registry.close(symbol, detected_date)

                group_key = (detected_date, symbol, strategy)
                seq_counter[group_key] += 1
                row_seq = seq_counter[group_key]

                cur.execute(
                    """
                    INSERT INTO closed_trades (
                        owner_id, account_id, position_id,
                        close_date, symbol, underlying,
                        strategy, structure, qty,
                        cost_basis, exit_value, realized_pnl, gain_pct,
                        row_seq, source
                    ) VALUES (
                        %(owner_id)s, %(account_id)s, %(position_id)s,
                        %(detected_date)s, %(symbol)s, %(underlying)s,
                        %(strategy)s, %(structure)s, %(qty)s,
                        %(cost_basis)s, %(last_value)s, %(est_realized_pnl)s,
                        CASE
                            WHEN %(cost_basis)s IS NOT NULL AND %(cost_basis)s <> 0
                            THEN round(
                                (%(est_realized_pnl)s / %(cost_basis)s) * 100, 4
                            )
                            ELSE NULL
                        END,
                        %(row_seq)s, 'csv_auto'
                    )
                    ON CONFLICT (account_id, close_date, symbol, strategy, row_seq)
                    DO NOTHING
                    """,
                    dict(
                        owner_id=owner_id,
                        account_id=account_id,
                        position_id=position_id,
                        detected_date=detected_date,
                        symbol=symbol,
                        underlying=underlying,
                        strategy=strategy,
                        structure=structure,
                        qty=qty,
                        cost_basis=cost_basis,
                        last_value=last_value,
                        est_realized_pnl=est_realized_pnl,
                        row_seq=row_seq,
                    ),
                )
                if cur.rowcount:
                    inserted_trades += 1

        print(
            f"pending_closes: {inserted_pending} log rows, "
            f"{inserted_trades} auto-promoted to closed_trades, "
            f"{skipped} skipped"
        )
