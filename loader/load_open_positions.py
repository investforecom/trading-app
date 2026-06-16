"""
Load open_positions.csv → positions + position_snapshots.

Each run of Routine A rewrites the file completely; this loader is idempotent:
re-running on the same file is a no-op (ON CONFLICT DO NOTHING on the snapshot row).
"""
import csv
from datetime import date
from pathlib import Path

from db import transaction, fetch_one
from util import (
    parse_decimal, parse_int, parse_date_csv, parse_flags,
    derive_underlying, safe_strategy, safe_theme,
)
from positions_registry import PositionsRegistry


def load(csv_path: Path, account_id: int, owner_id: int):
    with transaction() as cur:
        registry = PositionsRegistry(cur, owner_id, account_id)
        inserted_snapshots = 0
        skipped = 0
        auto_closed = 0

        # Remember which symbols were open BEFORE we process this CSV.
        # Any symbol that was open but absent from the new CSV will be closed
        # automatically — the routine rewrites the file on every run, so absence
        # means the position was exited or expired.
        open_before_csv = set(registry._open.keys())
        seen_in_csv: set[str] = set()
        snapshot_date_ref: date | None = None

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                snapshot_date = parse_date_csv(row["date"])
                symbol        = row["symbol"].strip()
                underlying    = row["underlying"].strip() or derive_underlying(symbol)
                strategy      = safe_strategy(row["strategy"])
                theme         = safe_theme(row["theme"])
                structure     = row["structure"].strip() or None
                qty           = parse_int(row["qty"])
                cost_basis    = parse_decimal(row["cost_basis"])
                current_value = parse_decimal(row["current_value"])
                gain_pct      = parse_decimal(row["gain_pct"])
                pct_nav       = parse_decimal(row["pct_nav"])
                forward_rr    = parse_decimal(row["forward_rr"])
                max_value     = parse_decimal(row["max_value"])
                mgmt_tier     = row["mgmt_tier"].strip() or None
                quality_rank  = row["quality_rank"].strip() or None
                flags         = parse_flags(row["flags"])
                notes         = row["notes"].strip() or None

                if not snapshot_date or not symbol:
                    skipped += 1
                    continue

                seen_in_csv.add(symbol)
                if snapshot_date_ref is None:
                    snapshot_date_ref = snapshot_date

                # Ensure the position exists (create if first time we see this symbol)
                pid = registry.get_or_create(
                    symbol=symbol,
                    underlying=underlying,
                    strategy=strategy,
                    theme=theme,
                    structure=structure,
                    opened_date=snapshot_date,  # best approximation from CSV
                    qty_at_open=qty,
                    cost_basis_at_open=cost_basis,
                )

                cur.execute(
                    """
                    INSERT INTO position_snapshots (
                        position_id, owner_id, snapshot_date,
                        qty, cost_basis, current_value, gain_pct, pct_nav,
                        forward_rr, max_value, mgmt_tier, quality_rank, flags, notes
                    ) VALUES (
                        %(position_id)s, %(owner_id)s, %(snapshot_date)s,
                        %(qty)s, %(cost_basis)s, %(current_value)s, %(gain_pct)s, %(pct_nav)s,
                        %(forward_rr)s, %(max_value)s, %(mgmt_tier)s, %(quality_rank)s,
                        %(flags)s, %(notes)s
                    )
                    ON CONFLICT (position_id, snapshot_date) DO NOTHING
                    """,
                    dict(
                        position_id=pid,
                        owner_id=owner_id,
                        snapshot_date=snapshot_date,
                        qty=qty,
                        cost_basis=cost_basis,
                        current_value=current_value,
                        gain_pct=gain_pct,
                        pct_nav=pct_nav,
                        forward_rr=forward_rr,
                        max_value=max_value,
                        mgmt_tier=mgmt_tier,
                        quality_rank=quality_rank,
                        flags=flags,
                        notes=notes,
                    ),
                )
                if cur.rowcount:
                    inserted_snapshots += 1
                else:
                    skipped += 1

        # Close any positions that were open before this run but are absent from
        # the new CSV. The routine rewrites the file completely each day, so a
        # missing symbol means the position was exited, expired, or assigned.
        if snapshot_date_ref:
            for symbol in open_before_csv - seen_in_csv:
                registry.close(symbol, snapshot_date_ref)
                auto_closed += 1
                print(f"  auto-closed: {symbol} (not in CSV as of {snapshot_date_ref})")

        print(f"open_positions: {inserted_snapshots} snapshots inserted, {skipped} skipped, {auto_closed} auto-closed")
