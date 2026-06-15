"""Load account_state.json → account_snapshots."""
import json
from pathlib import Path

from db import transaction
from util import parse_date_csv


def load(json_path: Path, account_id: int, owner_id: int):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    snapshot_date = parse_date_csv(data["date"])
    nav           = data.get("nav")
    cash          = data.get("cash")
    sgov          = data.get("sgov")
    deployed_pct  = data.get("deployed_pct")
    eff_leverage  = data.get("leverage")  # field is "leverage" in the JSON

    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO account_snapshots (
                owner_id, account_id, snapshot_date,
                nav, cash, sgov, deployed_pct, eff_leverage
            ) VALUES (
                %(owner_id)s, %(account_id)s, %(snapshot_date)s,
                %(nav)s, %(cash)s, %(sgov)s, %(deployed_pct)s, %(eff_leverage)s
            )
            ON CONFLICT (account_id, snapshot_date) DO NOTHING
            """,
            dict(
                owner_id=owner_id,
                account_id=account_id,
                snapshot_date=snapshot_date,
                nav=nav,
                cash=cash,
                sgov=sgov,
                deployed_pct=deployed_pct,
                eff_leverage=eff_leverage,
            ),
        )
        action = "inserted" if cur.rowcount else "already exists"
        print(f"account_state {snapshot_date}: {action}")
