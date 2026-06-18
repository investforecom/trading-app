-- 013_insights.sql
-- Layer 2: weekly behavioural analysis output.
-- Populated by run_analysis.py (Saturdays). Never written by Layer 1 loaders.

CREATE TABLE analysis_runs (
    id          SERIAL PRIMARY KEY,
    account_id  INT  NOT NULL REFERENCES accounts(id),
    run_date    DATE NOT NULL,
    run_type    TEXT NOT NULL DEFAULT 'weekly',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (account_id, run_date)
);

CREATE TABLE insights (
    id          SERIAL PRIMARY KEY,
    run_id      INT  NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    account_id  INT  NOT NULL REFERENCES accounts(id),
    category    TEXT NOT NULL,            -- STRATEGY | BEHAVIOR | WHEEL | SIZING | TREND
    severity    TEXT NOT NULL DEFAULT 'INFO',  -- INFO | WATCH | ACTION
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    metric_json JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX insights_run_idx     ON insights (run_id);
CREATE INDEX insights_account_idx ON insights (account_id, created_at DESC);
