"""
Main loader entrypoint.

Usage:
    python run.py [--repo PATH] [--flex PATH]

    --repo  Path to the trading-routine repo (default: ../trading-routine relative to this file)
    --flex  Path to a Flex Query CSV to load (optional; skip if not provided)

Environment variables required:
    PGHOST, PGDATABASE, PGUSER, PGPASSWORD
    PGPORT (optional, default 5432)

Run order:
    1. account_state.json         → account_snapshots
    2. closed_trades.csv          → closed_trades (source=csv, user-curated)
    3. pending_closes.csv         → pending_closes + auto-promote to closed_trades
    4. open_positions.csv         → positions + position_snapshots (current book)
    5. Flex Query CSV (if given)  → closed_trades (source=ibkr_flex, historical backfill)

Re-running is always safe: every insert uses ON CONFLICT DO NOTHING.
"""
import argparse
import sys
from pathlib import Path

from db import transaction, fetch_one
import load_account_state
import load_closed_trades
import load_pending_closes
import load_open_positions
import load_flex
import load_briefing
import load_position_overrides


def resolve_account(cur, ibkr_account_id: str) -> tuple[int, int]:
    """Return (owner_id, account_id) for a given IBKR account ID."""
    row = fetch_one(
        cur,
        "SELECT id, owner_id FROM accounts WHERE ibkr_account_id = %s",
        (ibkr_account_id,),
    )
    if not row:
        raise SystemExit(f"Account '{ibkr_account_id}' not found in DB. Run migrations first.")
    return row["owner_id"], row["id"]


def main():
    parser = argparse.ArgumentParser(description="Load trading data into Postgres")
    parser.add_argument(
        "--repo",
        default=str(Path(__file__).parent.parent.parent / "trading-routine"),
        help="Path to trading-routine repo",
    )
    parser.add_argument(
        "--flex",
        default=None,
        help="Path to IBKR Flex Query CSV for historical backfill",
    )
    args = parser.parse_args()

    repo = Path(args.repo)
    if not repo.exists():
        raise SystemExit(f"Repo not found: {repo}")

    # Resolve account IDs once
    with transaction() as cur:
        owner_id, account_id = resolve_account(cur, "U15760849")

    print(f"Loading into account_id={account_id}, owner_id={owner_id}\n")

    # 1. Account snapshot
    json_path = repo / "account_state.json"
    if json_path.exists():
        print("→ account_state.json")
        load_account_state.load(json_path, account_id, owner_id)
    else:
        print("  account_state.json not found, skipping")

    # 2. Closed trades CSV (user-curated, source of truth for confirmed closes)
    closed_path = repo / "closed_trades.csv"
    if closed_path.exists():
        print("\n→ closed_trades.csv")
        load_closed_trades.load(closed_path, account_id, owner_id)
    else:
        print("  closed_trades.csv not found, skipping")

    # 3. Pending closes (auto-promoted to closed_trades)
    pending_path = repo / "pending_closes.csv"
    if pending_path.exists():
        print("\n→ pending_closes.csv")
        load_pending_closes.load(pending_path, account_id, owner_id)
    else:
        print("  pending_closes.csv not found, skipping")

    # 4. Open positions (current book)
    open_path = repo / "open_positions.csv"
    if open_path.exists():
        print("\n→ open_positions.csv")
        load_open_positions.load(open_path, account_id, owner_id)
    else:
        print("  open_positions.csv not found, skipping")

    # 5. Flex Query historical backfill (optional)
    # Auto-select the flex file with the latest end-date from history/ when --flex not given.
    if args.flex:
        flex_path = Path(args.flex)
    else:
        candidates = sorted(
            (repo / "history").glob("U15760849_????????_????????.csv"),
            key=lambda p: p.stem.split("_")[2],  # sort by end-date field
        )
        flex_path = candidates[-1] if candidates else None
    if flex_path and flex_path.exists():
        print(f"\n→ Flex Query: {flex_path.name}")
        load_flex.load(flex_path, account_id, owner_id)
    else:
        print("\n  No Flex file found in history/, skipping")

    # 6. Position overrides (user notes + flag suppressions)
    overrides_path = repo / "position_overrides.csv"
    print("\n→ position_overrides.csv")
    load_position_overrides.load(overrides_path, account_id, owner_id)

    # 7. Daily briefings — load any not yet in DB (backfill on first run, then incremental)
    briefing_dir = repo / "briefing_log"
    if briefing_dir.exists():
        briefing_files = sorted(briefing_dir.glob("????-??-??.md"))
        if briefing_files:
            print(f"\n→ Briefings ({len(briefing_files)} files)")
            for bf in briefing_files:
                load_briefing.load(bf, account_id, owner_id)
        else:
            print("\n  No briefing files found, skipping")
    else:
        print("\n  briefing_log/ not found, skipping")

    print("\nDone.")


if __name__ == "__main__":
    main()
