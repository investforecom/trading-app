-- 017_ticker_caches.sql
-- Caches for the thesis builder's Quality Screen and Thesis stages. Both are
-- "current state" caches (upsert, one row per ticker) — not history like
-- investment_theses, which intentionally keeps every DCF run. The point is
-- to avoid re-pulling yfinance / re-calling Claude every time a saved ticker
-- is revisited; a row is only replaced when the user explicitly refreshes.

CREATE TABLE ticker_fundamentals_cache (
    owner_id    INT         NOT NULL REFERENCES owners(id),
    ticker      TEXT        NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_json   JSONB       NOT NULL,
    PRIMARY KEY (owner_id, ticker)
);

CREATE TABLE ticker_thesis_cache (
    owner_id            INT         NOT NULL REFERENCES owners(id),
    ticker              TEXT        NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    based_on_fetched_at TIMESTAMPTZ,  -- fundamentals_cache.fetched_at used as input, for staleness checks
    data_json           JSONB       NOT NULL,
    PRIMARY KEY (owner_id, ticker)
);
