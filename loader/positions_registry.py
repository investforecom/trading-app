"""
Position lifecycle manager.

Maintains a cache of (account_id, symbol) → position_id for open positions.
On first encounter of a symbol, creates the positions row.
On close, sets closed_date and removes from the open cache.
"""
from datetime import date
from typing import Optional
import psycopg2.extras


class PositionsRegistry:
    def __init__(self, cur, owner_id: int, account_id: int):
        self.cur = cur
        self.owner_id = owner_id
        self.account_id = account_id
        # symbol → position_id for currently open positions
        self._open: dict[str, int] = {}
        self._load_open()

    def _load_open(self):
        self.cur.execute(
            """
            SELECT id, symbol FROM positions
            WHERE account_id = %s AND closed_date IS NULL
            """,
            (self.account_id,),
        )
        for row in self.cur.fetchall():
            self._open[row["symbol"]] = row["id"]

    def get_or_create(
        self,
        symbol: str,
        underlying: str,
        strategy: str,
        theme: Optional[str],
        structure: Optional[str],
        opened_date: Optional[date],
        qty_at_open: Optional[int],
        cost_basis_at_open: Optional[float],
        source: str = "csv",
    ) -> int:
        """Return position_id for an open position, creating it if new."""
        if symbol in self._open:
            return self._open[symbol]

        self.cur.execute(
            """
            INSERT INTO positions (
                owner_id, account_id, symbol, underlying,
                strategy, theme, structure,
                opened_date, qty_at_open, cost_basis_at_open, source
            ) VALUES (
                %(owner_id)s, %(account_id)s, %(symbol)s, %(underlying)s,
                %(strategy)s, %(theme)s, %(structure)s,
                %(opened_date)s, %(qty_at_open)s, %(cost_basis_at_open)s, %(source)s
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            dict(
                owner_id=self.owner_id,
                account_id=self.account_id,
                symbol=symbol,
                underlying=underlying,
                strategy=strategy,
                theme=theme,
                structure=structure,
                opened_date=opened_date,
                qty_at_open=qty_at_open,
                cost_basis_at_open=cost_basis_at_open,
                source=source,
            ),
        )
        row = self.cur.fetchone()
        if row:
            pid = row["id"]
        else:
            # Race or duplicate — fetch existing open row
            self.cur.execute(
                """
                SELECT id FROM positions
                WHERE account_id = %s AND symbol = %s AND closed_date IS NULL
                """,
                (self.account_id, symbol),
            )
            pid = self.cur.fetchone()["id"]

        self._open[symbol] = pid
        return pid

    def close(self, symbol: str, closed_date: date) -> Optional[int]:
        """Mark open position as closed. Returns position_id or None if not tracked."""
        pid = self._open.pop(symbol, None)
        if pid is None:
            # Try DB in case it was opened before this loader run
            self.cur.execute(
                """
                SELECT id FROM positions
                WHERE account_id = %s AND symbol = %s AND closed_date IS NULL
                """,
                (self.account_id, symbol),
            )
            row = self.cur.fetchone()
            if row:
                pid = row["id"]

        if pid is not None:
            self.cur.execute(
                "UPDATE positions SET closed_date = %s WHERE id = %s",
                (closed_date, pid),
            )
        return pid

    def lookup_open(self, symbol: str) -> Optional[int]:
        return self._open.get(symbol)

    def lookup_any(self, symbol: str) -> Optional[int]:
        """Return most-recent position_id for symbol regardless of open/closed."""
        if symbol in self._open:
            return self._open[symbol]
        self.cur.execute(
            """
            SELECT id FROM positions
            WHERE account_id = %s AND symbol = %s
            ORDER BY COALESCE(opened_date, '1970-01-01') DESC, id DESC
            LIMIT 1
            """,
            (self.account_id, symbol),
        )
        row = self.cur.fetchone()
        return row["id"] if row else None
