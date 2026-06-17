-- Rename strategy_type enum value 'other' -> 'cash'.
-- Existing rows (lots, closed_trades, etc.) that stored 'other' automatically
-- reflect the new label after this ALTER — no row updates needed.
ALTER TYPE strategy_type RENAME VALUE 'other' TO 'cash';
