-- 005_position_snapshots.sql
-- One row per (position, date). Source: open_positions.csv rewritten each Routine A run.
-- forward_rr and max_value are NULL for uncapped positions (single-leg calls, shares).
-- flags stores the pipe-separated tokens from the CSV as a Postgres text array.

CREATE TABLE position_snapshots (
    id            SERIAL           PRIMARY KEY,
    position_id   INT              NOT NULL REFERENCES positions(id),
    owner_id      INT              NOT NULL REFERENCES owners(id),  -- denorm for tenant isolation
    snapshot_date DATE             NOT NULL,
    qty           INT              NOT NULL,
    cost_basis    NUMERIC(14,2)    NOT NULL,
    current_value NUMERIC(14,2),
    gain_pct      NUMERIC(10,4),   -- plain number, e.g. 23.50 (not 0.235)
    pct_nav       NUMERIC(10,4),   -- plain number, e.g. 4.10
    forward_rr    NUMERIC(10,4),   -- NULL when "N/A" (uncapped / shares)
    max_value     NUMERIC(14,2),   -- NULL when "N/A"
    mgmt_tier     mgmt_tier_type,
    quality_rank  quality_rank_type,
    flags         TEXT[],          -- e.g. '{HARVEST,THESIS_CHECK}'
    notes         TEXT,
    UNIQUE (position_id, snapshot_date)
);

CREATE INDEX position_snapshots_date_idx     ON position_snapshots (snapshot_date DESC);
CREATE INDEX position_snapshots_position_idx ON position_snapshots (position_id, snapshot_date DESC);
CREATE INDEX position_snapshots_owner_idx    ON position_snapshots (owner_id, snapshot_date DESC);
