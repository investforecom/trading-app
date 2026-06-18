-- 014_position_notes.sql
-- Bidirectional notes on positions: user context, flag suppressions, snooze dates.
-- Source: position_overrides.csv in trading-routine repo → loaded by load_position_overrides.py
-- Layer 1 loaders (flags, positions) join this table to suppress flagged items.
-- run_analysis.py reads suppress_flags before generating insights.

CREATE TABLE position_notes (
    id              SERIAL PRIMARY KEY,
    account_id      INT     NOT NULL REFERENCES accounts(id),
    underlying      TEXT    NOT NULL,
    strategy        TEXT,                -- NULL = applies to all strategies for this underlying
    note            TEXT    NOT NULL,    -- user-provided context / thesis reminder
    suppress_flags  TEXT[]  DEFAULT '{}', -- e.g. ARRAY['HARVEST','TRIM'] — skipped while active
    snooze_until    DATE,                -- NULL = suppress indefinitely; set a date to auto-expire
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX position_notes_underlying_strategy_idx
    ON position_notes (account_id, underlying, COALESCE(strategy, ''));

-- narrative column on analysis_runs: AI-generated plain-text summary stored alongside insights
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS narrative TEXT;
