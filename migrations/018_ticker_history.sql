-- 018_ticker_history.sql
-- Supersedes the "current state" caches from 017 with proper append-only
-- history, matching investment_theses' pattern — every fetch/generate is a
-- new row, "current" is just the latest one. Lets the Quality Screen and
-- Thesis stages support the same click-to-revisit history the DCF stage
-- already has. No real data depends on the 017 shape yet (test fetches
-- only), so this replaces rather than migrates it.

DROP TABLE IF EXISTS ticker_fundamentals_cache;
DROP TABLE IF EXISTS ticker_thesis_cache;

CREATE TABLE ticker_fundamentals_snapshots (
    id            SERIAL        PRIMARY KEY,
    owner_id      INT           NOT NULL REFERENCES owners(id),
    ticker        TEXT          NOT NULL,
    fetched_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    current_price NUMERIC(14,4),
    data_json     JSONB         NOT NULL
);

CREATE INDEX ticker_fundamentals_snapshots_idx ON ticker_fundamentals_snapshots (owner_id, ticker, fetched_at DESC);

CREATE TABLE ticker_thesis_snapshots (
    id                  SERIAL        PRIMARY KEY,
    owner_id            INT           NOT NULL REFERENCES owners(id),
    ticker              TEXT          NOT NULL,
    generated_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    based_on_fetched_at TIMESTAMPTZ,  -- fundamentals snapshot used as input, for staleness checks
    data_json           JSONB         NOT NULL
);

CREATE INDEX ticker_thesis_snapshots_idx ON ticker_thesis_snapshots (owner_id, ticker, generated_at DESC);
