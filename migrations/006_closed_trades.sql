-- 006_closed_trades.sql
-- Append-only realized trade ledger.
--
-- Sources:
--   'csv'        closed_trades.csv (user-curated, manually promoted from pending_closes.csv)
--   'csv_auto'   auto-promoted from pending_closes.csv (no manual confirmation)
--   'ibkr_flex'  Flex Query EXECUTION close rows or Option Exercises section
--
-- Dual idempotency:
--   ibkr_flex rows: ibkr_exec_id UNIQUE (one exec ID per execution, globally unique)
--   csv rows:       (account_id, close_date, symbol, strategy, row_seq)
--                   row_seq increments within the group to handle partial closes
--                   on the same day for the same symbol/strategy

CREATE TABLE closed_trades (
    id             SERIAL          PRIMARY KEY,
    owner_id       INT             NOT NULL REFERENCES owners(id),
    account_id     INT             NOT NULL REFERENCES accounts(id),
    position_id    INT             REFERENCES positions(id),  -- NULL when linkage not resolvable
    close_date     DATE            NOT NULL,
    open_date      DATE,                                       -- NULL = unknown (old CSV records)
    symbol         TEXT            NOT NULL,
    underlying     TEXT            NOT NULL,  -- own column; loader derives or gets from Flex
    strategy       strategy_type   NOT NULL,
    structure      TEXT,
    qty            INT             NOT NULL,  -- abs value; direction inferred from Buy/Sell
    cost_basis     NUMERIC(14,2)   NOT NULL,
    exit_value     NUMERIC(14,2)   NOT NULL,
    realized_pnl   NUMERIC(14,2)   NOT NULL,  -- signed; strip leading "+" on CSV load
    gain_pct       NUMERIC(10,4)   NOT NULL,
    hold_days      INT,                        -- NULL = unknown (old CSV records)
    exit_reason    TEXT,
    ibkr_exec_id   TEXT            UNIQUE,     -- NULL for csv/csv_auto rows
    row_seq        SMALLINT        NOT NULL DEFAULT 1,
    source         TEXT            NOT NULL DEFAULT 'csv',
    UNIQUE (account_id, close_date, symbol, strategy, row_seq)
);

CREATE INDEX closed_trades_account_date_idx    ON closed_trades (account_id, close_date DESC);
CREATE INDEX closed_trades_underlying_idx      ON closed_trades (account_id, underlying);
CREATE INDEX closed_trades_strategy_idx        ON closed_trades (account_id, strategy);
CREATE INDEX closed_trades_position_idx        ON closed_trades (position_id);
