-- Daily briefing store: header metrics + decisions + flagged positions.
-- Populated by load_briefing.py after each routine run.
-- daily_briefings  — one row per day per account (header metrics + full md)
-- daily_decisions  — up to 4 ranked action items per briefing
-- daily_flags      — flagged positions (HARVEST / UNDERWATER / TRIM / etc.)

CREATE TABLE daily_briefings (
    id              SERIAL PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    date            DATE NOT NULL,
    nav             NUMERIC(12,2),
    deployed_pct    NUMERIC(5,2),
    eff_lev         NUMERIC(5,3),
    band_lo         NUMERIC(5,2),
    band_hi         NUMERIC(5,2),
    wheel_cover     TEXT,
    commentary      TEXT,
    market_summary  TEXT,
    wheel_section   TEXT,
    watchlist       TEXT,
    briefing_md     TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (account_id, date)
);

CREATE TABLE daily_decisions (
    id              SERIAL PRIMARY KEY,
    briefing_id     INTEGER NOT NULL REFERENCES daily_briefings(id) ON DELETE CASCADE,
    rank            INTEGER NOT NULL,
    decision_text   TEXT NOT NULL
);

CREATE TABLE daily_flags (
    id              SERIAL PRIMARY KEY,
    briefing_id     INTEGER NOT NULL REFERENCES daily_briefings(id) ON DELETE CASCADE,
    flag_type       TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    note            TEXT,
    CONSTRAINT flag_type_check CHECK (
        flag_type IN ('HARVEST','UNDERWATER','TRIM','THESIS-CHECK','EXPIRES','NEW','OTHER')
    )
);

-- Convenience view: latest briefing per account
CREATE VIEW latest_briefing AS
SELECT DISTINCT ON (account_id)
    b.*,
    o.ibkr_account_id
FROM daily_briefings b
JOIN accounts o ON o.id = b.account_id
ORDER BY account_id, date DESC;

-- Convenience view: today's decisions with briefing date
CREATE VIEW todays_decisions AS
SELECT
    b.date,
    b.nav,
    b.deployed_pct,
    b.eff_lev,
    d.rank,
    d.decision_text
FROM daily_decisions d
JOIN daily_briefings b ON b.id = d.briefing_id
JOIN (
    SELECT account_id, MAX(date) AS latest
    FROM daily_briefings
    GROUP BY account_id
) mx ON mx.account_id = b.account_id AND mx.latest = b.date
ORDER BY d.rank;
