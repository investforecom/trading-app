-- 015_theme_text.sql
-- Convert theme columns from the theme_type enum to plain TEXT.
--
-- Rationale: themes evolve frequently (consolidations, new sectors). A TEXT
-- column avoids the ALTER TYPE ... ADD VALUE ceremony on every change and
-- lets the application treat themes as a soft taxonomy rather than a hard
-- schema constraint.
--
-- Applied manually 2026-08-05. This migration is idempotent: the IF EXISTS
-- guards make it safe to re-run on a fresh DB built from all migrations in
-- order (001 creates theme_type; this migration drops it).

BEGIN;

-- Drop views that reference the enum columns so we can ALTER the base tables.
DROP VIEW IF EXISTS current_positions CASCADE;
DROP VIEW IF EXISTS flagged_positions  CASCADE;
DROP VIEW IF EXISTS open_lots          CASCADE;

-- Convert base tables.
ALTER TABLE positions ALTER COLUMN theme TYPE TEXT USING theme::TEXT;
ALTER TABLE lots      ALTER COLUMN theme TYPE TEXT USING theme::TEXT;

-- Remove the enum type (no longer referenced by any column).
DROP TYPE IF EXISTS theme_type;

-- Recreate views (identical SQL to 008_views.sql and 009_lots.sql; theme is
-- now TEXT so no cast needed).

CREATE VIEW current_positions AS
SELECT DISTINCT ON (ps.position_id)
    p.id            AS position_id,
    p.symbol,
    p.underlying,
    p.strategy,
    p.theme,
    p.structure,
    p.opened_date,
    p.thesis,
    p.catalyst,
    p.invalidation,
    p.entry_score,
    ps.snapshot_date,
    ps.qty,
    ps.cost_basis,
    ps.current_value,
    ps.gain_pct,
    ps.pct_nav,
    ps.forward_rr,
    ps.max_value,
    ps.mgmt_tier,
    ps.quality_rank,
    ps.flags,
    ps.notes,
    a.ibkr_account_id,
    o.display_name  AS owner
FROM position_snapshots ps
JOIN positions p ON p.id        = ps.position_id
JOIN accounts  a ON a.id        = p.account_id
JOIN owners    o ON o.id        = p.owner_id
WHERE p.closed_date IS NULL
ORDER BY ps.position_id, ps.snapshot_date DESC;

CREATE VIEW flagged_positions AS
SELECT
    p.symbol,
    p.underlying,
    p.strategy,
    p.theme,
    ps.snapshot_date,
    ps.gain_pct,
    ps.pct_nav,
    ps.forward_rr,
    ps.mgmt_tier,
    ps.quality_rank,
    ps.flags,
    ps.notes,
    a.ibkr_account_id
FROM position_snapshots ps
JOIN positions p ON p.id = ps.position_id
JOIN accounts  a ON a.id = p.account_id
WHERE p.closed_date IS NULL
  AND ps.snapshot_date = (SELECT max(snapshot_date) FROM position_snapshots)
  AND ps.flags IS NOT NULL
  AND array_length(ps.flags, 1) > 0
ORDER BY ps.pct_nav DESC;

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

COMMIT;
