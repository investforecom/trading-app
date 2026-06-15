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

CREATE TYPE theme_type AS ENUM (
    'AI-DC',
    'AI-Semis',
    'AI-Storage',
    'Neo-Cloud',
    'Large-Cap-Tech',
    'Fintech',
    'Financials',
    'Software-Recovery',
    'Nuclear-Power',
    'Solar-Energy',
    'Nat-Gas',
    'Battery-Storage',
    'Drones-Defense',
    'Gold-Macro',
    'Crit-Minerals',
    'Consumer',
    'Edge-HPC',
    'Quantum',
    'Photonics',
    'Autonomous-SW',
    'Space',
    'Crypto-Bitcoin',
    'Healthcare',
    'Cybersecurity',
    'Income',
    'Cash'
);

CREATE TYPE mgmt_tier_type AS ENUM ('Runner', 'Monitor', 'On-notice');

CREATE TYPE quality_rank_type AS ENUM ('A', 'B', 'C');
