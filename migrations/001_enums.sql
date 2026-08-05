-- 001_enums.sql
-- All domain enum types. Add new values with ALTER TYPE ... ADD VALUE; never remove.

CREATE TYPE strategy_type AS ENUM (
    'LEAP',
    'LDS',
    'SWING',
    '2x-ETF',
    'Thematic',
    'WheelSP',
    'WheelSC',
    'PCS',      -- retired; kept for historical data only
    'other'
);

-- theme_type enum removed in 015_theme_text.sql (2026-08-05).
-- Theme is now a plain TEXT column — no schema change needed to add/rename themes.

CREATE TYPE mgmt_tier_type AS ENUM ('Runner', 'Monitor', 'On-notice');

CREATE TYPE quality_rank_type AS ENUM ('A', 'B', 'C');
