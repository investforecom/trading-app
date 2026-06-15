-- 008_views.sql
-- Read-only views for Metabase and any other consumer.
-- These cost nothing to store; drop and recreate freely when schema evolves.

-- Live book: latest snapshot per open position.
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

-- Equity curve: NAV and deployment over time.
CREATE VIEW equity_curve AS
SELECT
    s.snapshot_date,
    s.nav,
    s.cash,
    s.sgov,
    s.deployed_pct,
    s.eff_leverage,
    a.ibkr_account_id,
    o.display_name AS owner
FROM account_snapshots s
JOIN accounts a ON a.id = s.account_id
JOIN owners   o ON o.id = s.owner_id
ORDER BY s.snapshot_date;

-- Per-strategy P&L summary from closed trades.
CREATE VIEW strategy_pnl AS
SELECT
    a.ibkr_account_id,
    ct.strategy,
    count(*)                                AS trade_count,
    count(*) FILTER (WHERE realized_pnl > 0) AS wins,
    count(*) FILTER (WHERE realized_pnl < 0) AS losses,
    round(
        100.0 * count(*) FILTER (WHERE realized_pnl > 0) / count(*), 1
    )                                       AS win_rate_pct,
    round(sum(realized_pnl)::NUMERIC, 2)   AS total_pnl,
    round(avg(realized_pnl)::NUMERIC, 2)   AS avg_pnl,
    round(avg(gain_pct)::NUMERIC, 2)       AS avg_gain_pct,
    round(avg(hold_days)::NUMERIC, 1)      AS avg_hold_days
FROM closed_trades ct
JOIN accounts a ON a.id = ct.account_id
GROUP BY a.ibkr_account_id, ct.strategy
ORDER BY total_pnl DESC;

-- Flagged positions (current day only) — feed for the dashboard alert panel.
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
  AND ps.snapshot_date = (
        SELECT max(snapshot_date) FROM position_snapshots
      )
  AND ps.flags IS NOT NULL
  AND array_length(ps.flags, 1) > 0
ORDER BY ps.pct_nav DESC;
