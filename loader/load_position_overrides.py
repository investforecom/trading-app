"""
Load position_overrides.csv → position_notes table.

CSV format (headers required):
    underlying, strategy, note, suppress_flags, snooze_until

Field notes:
    underlying      ticker, e.g. OSS
    strategy        optional — leave blank to apply to all strategies
    note            free text; use semicolons not commas
    suppress_flags  pipe-separated flag tokens, e.g. HARVEST|TRIM  (blank = none)
    snooze_until    YYYY-MM-DD or blank (blank = suppress indefinitely)

Idempotent: upserts on (account_id, underlying, strategy).
"""
import csv
from datetime import date
from pathlib import Path

from db import transaction


def load(path: Path, account_id: int, _owner_id: int) -> None:
    if not path.exists():
        print("  position_overrides.csv not found, skipping")
        return

    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            underlying = r.get("underlying", "").strip().upper()
            if not underlying or underlying.startswith("#"):
                continue
            strategy = r.get("strategy", "").strip() or None
            note = r.get("note", "").strip()
            if not note:
                continue
            raw_flags = r.get("suppress_flags", "").strip()
            suppress_flags = [f.strip() for f in raw_flags.split("|") if f.strip()] if raw_flags else []
            raw_snooze = r.get("snooze_until", "").strip()
            snooze_until = None
            if raw_snooze:
                try:
                    snooze_until = date.fromisoformat(raw_snooze)
                except ValueError:
                    pass
            rows.append((underlying, strategy, note, suppress_flags, snooze_until))

    inserted = updated = 0
    with transaction() as cur:
        for underlying, strategy, note, suppress_flags, snooze_until in rows:
            cur.execute("""
                INSERT INTO position_notes
                    (account_id, underlying, strategy, note, suppress_flags, snooze_until, active, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, TRUE, NOW())
                ON CONFLICT (account_id, underlying, COALESCE(strategy, ''))
                DO UPDATE SET
                    note           = EXCLUDED.note,
                    suppress_flags = EXCLUDED.suppress_flags,
                    snooze_until   = EXCLUDED.snooze_until,
                    active         = TRUE,
                    updated_at     = NOW()
                WHERE position_notes.note           IS DISTINCT FROM EXCLUDED.note
                   OR position_notes.suppress_flags IS DISTINCT FROM EXCLUDED.suppress_flags
                   OR position_notes.snooze_until   IS DISTINCT FROM EXCLUDED.snooze_until
            """, (account_id, underlying, strategy, suppress_flags, snooze_until, note))
            if cur.rowcount > 0:
                updated += 1
            else:
                inserted += 0  # no-op counts as 0 change

    print(f"  position_overrides: {len(rows)} rows processed, {updated} changed")
