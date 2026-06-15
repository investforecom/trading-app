-- 003_account_snapshots.sql
-- Daily NAV/deployment snapshot. Source: account_state.json written by Routine A.
-- eff_leverage = (gross_position_value - sgov) / nav  (never IBKR raw leverage)

CREATE TABLE account_snapshots (
    id            SERIAL       PRIMARY KEY,
    owner_id      INT          NOT NULL REFERENCES owners(id),
    account_id    INT          NOT NULL REFERENCES accounts(id),
    snapshot_date DATE         NOT NULL,
    nav           NUMERIC(14,2),
    cash          NUMERIC(14,2),   -- can be negative (slight margin)
    sgov          NUMERIC(14,2),
    deployed_pct  NUMERIC(7,4),    -- e.g. 57.83
    eff_leverage  NUMERIC(7,4),    -- e.g. 1.063
    UNIQUE (account_id, snapshot_date)
);

CREATE INDEX account_snapshots_date_idx ON account_snapshots (account_id, snapshot_date DESC);
