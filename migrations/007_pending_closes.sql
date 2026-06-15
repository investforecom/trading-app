-- 007_pending_closes.sql
-- Event log of positions the routine detected as disappeared.
-- No manual confirmation step: loader auto-inserts into closed_trades at the same time.
-- This table is an audit trail only ("routine saw this disappear on this date").

CREATE TABLE pending_closes (
    id               SERIAL         PRIMARY KEY,
    owner_id         INT            NOT NULL REFERENCES owners(id),
    account_id       INT            NOT NULL REFERENCES accounts(id),
    position_id      INT            REFERENCES positions(id),
    detected_date    DATE           NOT NULL,
    symbol           TEXT           NOT NULL,
    underlying       TEXT           NOT NULL,
    strategy         strategy_type,
    structure        TEXT,
    qty              INT            NOT NULL,
    cost_basis       NUMERIC(14,2),
    last_value       NUMERIC(14,2),       -- can be negative (short position MtM)
    est_realized_pnl NUMERIC(14,2),       -- strip leading "+" on load
    likely_reason    TEXT,
    status           TEXT           NOT NULL DEFAULT 'auto_confirmed',
    resolved_date    DATE,
    CONSTRAINT pending_closes_status_ck CHECK (status IN ('auto_confirmed', 'dismissed')),
    UNIQUE (account_id, detected_date, symbol)
);

CREATE INDEX pending_closes_account_idx ON pending_closes (account_id, detected_date DESC);
