-- 004_positions.sql
-- One row per position opening episode. A symbol that closes and re-opens gets a new row.
--
-- Lifecycle:
--   opened_date set when first seen in open_positions.csv (or from Flex OpenDateTime)
--   closed_date set when the position is confirmed closed (from closed_trades or pending_closes)
--
-- Thesis/catalyst/invalidation are populated manually or via future UI; NULL on initial load.

CREATE TABLE positions (
    id                  SERIAL          PRIMARY KEY,
    owner_id            INT             NOT NULL REFERENCES owners(id),
    account_id          INT             NOT NULL REFERENCES accounts(id),
    symbol              TEXT            NOT NULL,  -- full contract key, e.g. ORCL_DEC27_170C270C
    underlying          TEXT            NOT NULL,  -- base ticker, own column: e.g. ORCL, SGOV
    strategy            strategy_type   NOT NULL,
    theme               theme_type,
    structure           TEXT,                      -- "170C/270C spread", "shares", "23.5P short"
    opened_date         DATE,                      -- NULL for pre-history imports
    closed_date         DATE,                      -- NULL while open
    qty_at_open         INT,
    cost_basis_at_open  NUMERIC(14,2),
    -- Populated manually or via future workflow; empty on initial CSV/Flex load:
    thesis              TEXT,
    catalyst            TEXT,       -- NULL if no specific catalyst
    invalidation        TEXT,       -- written invalidation condition at entry
    entry_score         SMALLINT,   -- §8 scoring rubric sum
    source              TEXT        NOT NULL DEFAULT 'csv',  -- 'csv' | 'ibkr_flex'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- At most one OPEN episode per (account, symbol) at any time.
-- Closed episodes are unconstrained, allowing re-opens of the same symbol.
CREATE UNIQUE INDEX positions_one_open_per_symbol
    ON positions (account_id, symbol)
    WHERE closed_date IS NULL;

CREATE INDEX positions_account_underlying_idx ON positions (account_id, underlying);
CREATE INDEX positions_closed_date_idx        ON positions (account_id, closed_date);
