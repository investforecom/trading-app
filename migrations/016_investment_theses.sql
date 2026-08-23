-- 016_investment_theses.sql
-- Investment thesis builder: fundamentals snapshot + DCF assumptions/outputs +
-- Claude-generated written thesis, risks, and scenario fair values.
--
-- One row per generation run — rows are never overwritten, so past theses can
-- be revisited and compared against how the name actually performed.
-- fundamentals_json and dcf_*_json are captured at generation time so a saved
-- run can be reloaded without re-pulling from yfinance or re-running the DCF.

CREATE TABLE investment_theses (
    id                 SERIAL        PRIMARY KEY,
    owner_id           INT           NOT NULL REFERENCES owners(id),
    ticker             TEXT          NOT NULL,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),

    current_price      NUMERIC(14,4),
    fundamentals_json  JSONB         NOT NULL,   -- cleaned yfinance snapshot
    dcf_inputs_json    JSONB         NOT NULL,   -- bear/base/bull assumptions used
    dcf_outputs_json   JSONB         NOT NULL,   -- per-scenario projection + sensitivity table

    fair_value_bear    NUMERIC(14,4),
    fair_value_base    NUMERIC(14,4),
    fair_value_bull    NUMERIC(14,4),
    target_price       NUMERIC(14,4),            -- Claude's probability-weighted call

    thesis_text        TEXT,
    risks_json         JSONB                     -- [{title, detail}, ...]
);

CREATE INDEX investment_theses_ticker_idx ON investment_theses (ticker, created_at DESC);
CREATE INDEX investment_theses_owner_idx  ON investment_theses (owner_id, created_at DESC);
