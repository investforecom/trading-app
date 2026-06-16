-- 009_lots.sql
-- Full Lots Model: every purchase tranche is tracked from open to close.
-- Enables per-lot hold-day accuracy, partial-close tracking, and
-- FIFO cost-basis reconciliation against IBKR.

-- ---------------------------------------------------------------------------
-- lots: one row per opening event (purchase tranche)
-- ---------------------------------------------------------------------------
CREATE TABLE lots (
    id                          SERIAL PRIMARY KEY,
    owner_id                    INTEGER NOT NULL REFERENCES owners(id),
    account_id                  INTEGER NOT NULL REFERENCES accounts(id),
    position_id                 INTEGER REFERENCES positions(id),

    symbol                      TEXT NOT NULL,
    underlying                  TEXT NOT NULL,
    strategy                    strategy_type NOT NULL,
    theme                       theme_type,
    structure                   TEXT,

    -- Purchase details
    open_date                   DATE NOT NULL,
    open_ts                     TIMESTAMPTZ NOT NULL,   -- full precision from IBKR OpenDateTime
    qty                         INTEGER NOT NULL,       -- original size of this lot
    cost_per_unit               NUMERIC(14,6),
    cost_basis                  NUMERIC(14,2),          -- abs(qty × cost_per_unit)

    -- Remaining qty: starts = qty; decrements as partial closes are recorded
    remaining_qty               INTEGER NOT NULL,

    -- IBKR tracking (populated from open-positions LOT rows, NULL for reconstructed lots)
    ibkr_originating_order_id   TEXT,
    ibkr_originating_txn_id     TEXT,

    source                      TEXT NOT NULL DEFAULT 'ibkr_flex',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Primary deduplication: each opening event has a unique timestamp per symbol/account
    UNIQUE (account_id, symbol, open_ts)
);

-- Secondary dedup: OriginatingTransactionID is unique when present
CREATE UNIQUE INDEX lots_originating_txn_idx
    ON lots(account_id, ibkr_originating_txn_id)
    WHERE ibkr_originating_txn_id IS NOT NULL;

CREATE INDEX lots_underlying_idx ON lots(account_id, underlying, open_date);
CREATE INDEX lots_position_idx   ON lots(position_id) WHERE position_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- lot_closes: each event where a lot (or portion of one) is closed
-- Sourced from CLOSED_LOT rows in the Flex Trades section.
-- ---------------------------------------------------------------------------
CREATE TABLE lot_closes (
    id              SERIAL PRIMARY KEY,
    lot_id          INTEGER NOT NULL REFERENCES lots(id),
    owner_id        INTEGER NOT NULL,
    account_id      INTEGER NOT NULL,
    closed_trade_id INTEGER REFERENCES closed_trades(id),  -- the EXECUTION row; NULL for expirations

    open_date       DATE NOT NULL,     -- denormalized from lot (avoids a join for hold_days)
    close_date      DATE NOT NULL,
    qty_closed      INTEGER NOT NULL,  -- always positive
    cost_basis      NUMERIC(14,2),
    realized_pnl    NUMERIC(14,2),
    hold_days       INTEGER,           -- close_date - open_date, set on insert

    ibkr_order_id   TEXT,              -- IBOrderID from CLOSED_LOT row; NULL for expirations/assignments
    source          TEXT NOT NULL DEFAULT 'ibkr_flex',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- When IBOrderID is present: one record per (lot, order)
CREATE UNIQUE INDEX lot_closes_with_order_idx
    ON lot_closes(lot_id, ibkr_order_id)
    WHERE ibkr_order_id IS NOT NULL;

-- When IBOrderID is absent (expiration / assignment): one record per (lot, date)
CREATE UNIQUE INDEX lot_closes_no_order_idx
    ON lot_closes(lot_id, close_date)
    WHERE ibkr_order_id IS NULL;

CREATE INDEX lot_closes_lot_idx   ON lot_closes(lot_id);
CREATE INDEX lot_closes_trade_idx ON lot_closes(closed_trade_id) WHERE closed_trade_id IS NOT NULL;
CREATE INDEX lot_closes_date_idx  ON lot_closes(close_date);


-- ---------------------------------------------------------------------------
-- open_lots: currently open lots (remaining_qty > 0)
-- ---------------------------------------------------------------------------
CREATE VIEW open_lots AS
SELECT
    l.id                                                            AS lot_id,
    l.position_id,
    l.symbol,
    l.underlying,
    l.strategy,
    l.theme,
    l.structure,
    l.open_date,
    l.open_ts,
    l.qty                                                           AS original_qty,
    l.remaining_qty,
    l.cost_per_unit,
    l.cost_basis                                                    AS original_cost_basis,
    ROUND(
        (l.remaining_qty::NUMERIC / NULLIF(l.qty, 0)) * l.cost_basis, 2
    )                                                               AS remaining_cost_basis,
    a.ibkr_account_id,
    o.display_name                                                  AS owner
FROM lots l
JOIN accounts a ON a.id = l.account_id
JOIN owners   o ON o.id = l.owner_id
WHERE l.remaining_qty > 0
ORDER BY l.underlying, l.open_date;


-- ---------------------------------------------------------------------------
-- lot_performance: closed lot records with per-lot P&L and hold days
-- ---------------------------------------------------------------------------
CREATE VIEW lot_performance AS
SELECT
    l.symbol,
    l.underlying,
    l.strategy,
    l.open_date,
    l.qty                                                           AS lot_qty,
    l.remaining_qty,
    l.cost_basis                                                    AS lot_cost_basis,
    lc.close_date,
    lc.qty_closed,
    lc.cost_basis                                                   AS close_cost_basis,
    lc.realized_pnl,
    lc.hold_days,
    ROUND(
        100.0 * lc.realized_pnl / NULLIF(ABS(lc.cost_basis), 0), 2
    )                                                               AS gain_pct,
    a.ibkr_account_id,
    o.display_name                                                  AS owner
FROM lot_closes lc
JOIN lots     l ON l.id  = lc.lot_id
JOIN accounts a ON a.id  = lc.account_id
JOIN owners   o ON o.id  = lc.owner_id
ORDER BY l.underlying, lc.close_date;
