#!/usr/bin/env python3
"""
build_dashboard.py — Builds the Trading Insights Metabase dashboard.

Creates 4 sections: Today's Brief · Portfolio · Analytics · Wheel Income · Risk
Run once to create; re-run will create a new dashboard (old one is left intact).
"""

import sys
import requests

MB    = "http://127.0.0.1:80"
TOKEN = "a0b0b634-f7ab-42ab-9f3f-6af330b6ffa7"
DB_ID = 2

HDR = {"X-Metabase-Session": TOKEN, "Content-Type": "application/json"}


def mb(method, path, body=None):
    r = getattr(requests, method)(f"{MB}/api{path}", headers=HDR, json=body)
    if not r.ok:
        print(f"  ERR {method.upper()} {path}  {r.status_code}: {r.text[:400]}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


def card(name, sql, display, vs=None):
    return mb("post", "/card", {
        "name": name,
        "dataset_query": {
            "type": "native",
            "native": {"query": sql.strip()},
            "database": DB_ID,
        },
        "display": display,
        "visualization_settings": vs or {},
    })


_next_id = -1  # counter for temporary dashcard IDs
_dashcards = []  # accumulated dashcards for the batch PUT


def _new_id():
    global _next_id
    _id = _next_id
    _next_id -= 1
    return _id


def place(card_id, row, col, sx, sy, vs=None):
    _dashcards.append({
        "id": _new_id(),
        "card_id": card_id,
        "row": row, "col": col, "size_x": sx, "size_y": sy,
        "parameter_mappings": [],
        "visualization_settings": vs or {},
        "series": [],
    })


def heading(text, row, col, sx, sy):
    _dashcards.append({
        "id": _new_id(),
        "card_id": None,
        "row": row, "col": col, "size_x": sx, "size_y": sy,
        "parameter_mappings": [],
        "visualization_settings": {
            "virtual_card": {"display": "heading"},
            "text": text,
        },
        "series": [],
    })


def flush_to_dashboard(did):
    return mb("put", f"/dashboard/{did}", {"dashcards": _dashcards})


# ── SQL DEFINITIONS ────────────────────────────────────────────────────────────

S = {}  # SQL registry

# ── Section 1: TODAY'S BRIEF ─────────────────────────────────────────────────

S["nav"] = """
SELECT nav AS "NAV ($)"
FROM daily_briefings
ORDER BY date DESC LIMIT 1
"""

S["deployed_pct"] = """
SELECT deployed_pct AS "Deployed %"
FROM daily_briefings
ORDER BY date DESC LIMIT 1
"""

S["eff_lev"] = """
SELECT eff_lev AS "Eff Lev"
FROM daily_briefings
ORDER BY date DESC LIMIT 1
"""

S["free_capital"] = """
SELECT
    ROUND((nav * (1 - eff_lev))::numeric, 0) AS "Free Capital ($)"
FROM daily_briefings
ORDER BY date DESC LIMIT 1
"""

S["decisions"] = """
SELECT
    d.rank          AS "#",
    d.decision_text AS "Action"
FROM daily_decisions d
JOIN daily_briefings b ON b.id = d.briefing_id
WHERE b.date = (SELECT MAX(date) FROM daily_briefings)
ORDER BY d.rank
"""

S["flags"] = """
SELECT
    f.flag_type AS "Type",
    f.symbol    AS "Ticker",
    f.note      AS "Note"
FROM daily_flags f
JOIN daily_briefings b ON b.id = f.briefing_id
WHERE b.date = (SELECT MAX(date) FROM daily_briefings)
ORDER BY
    CASE f.flag_type
        WHEN 'HARVEST'      THEN 1
        WHEN 'TRIM'         THEN 2
        WHEN 'UNDERWATER'   THEN 3
        WHEN 'THESIS-CHECK' THEN 4
        ELSE 5
    END,
    f.symbol
"""

# ── Section 2: PORTFOLIO ─────────────────────────────────────────────────────

S["open_positions"] = """
SELECT
    p.underlying                                                  AS "Ticker",
    p.strategy                                                    AS "Strategy",
    ps.qty                                                        AS "Qty",
    ROUND(ps.cost_basis::numeric, 0)                             AS "Cost ($)",
    ROUND(ps.current_value::numeric, 0)                          AS "Value ($)",
    ROUND(ps.gain_pct::numeric, 1)                               AS "Gain %",
    ROUND(ps.pct_nav::numeric, 1)                                AS "% NAV",
    CASE WHEN ps.forward_rr IS NOT NULL
         THEN ROUND(ps.forward_rr::numeric, 2)::text
         ELSE 'N/A' END                                          AS "Fwd R/R",
    COALESCE(array_to_string(ps.flags, ' | '), '')               AS "Flags"
FROM position_snapshots ps
JOIN positions p ON p.id = ps.position_id
WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
  AND p.strategy <> 'cash'
ORDER BY ps.pct_nav DESC NULLS LAST
"""

S["allocation"] = """
SELECT
    p.strategy                                   AS "Strategy",
    ROUND(SUM(ps.current_value)::numeric, 0)    AS "Value ($)"
FROM position_snapshots ps
JOIN positions p ON p.id = ps.position_id
WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
  AND p.strategy <> 'cash'
GROUP BY p.strategy
ORDER BY "Value ($)" DESC
"""

S["nav_history"] = """
SELECT
    date   AS "Date",
    nav    AS "NAV ($)"
FROM daily_briefings
ORDER BY date
"""

S["deployed_history"] = """
SELECT
    date                AS "Date",
    deployed_pct        AS "Deployed %",
    band_lo             AS "Band Low",
    band_hi             AS "Band High"
FROM daily_briefings
ORDER BY date
"""

# ── Section 3: ANALYTICS ─────────────────────────────────────────────────────

S["strategy_scorecard"] = """
SELECT
    strategy                                                          AS "Strategy",
    COUNT(*)                                                          AS "Trades",
    ROUND(SUM(realized_pnl)::numeric, 0)                            AS "Total P&L ($)",
    ROUND(AVG(gain_pct)::numeric, 1)                                 AS "Avg Gain %",
    ROUND(
        100.0 * COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)
        / NULLIF(COUNT(*), 0)::numeric, 0
    )                                                                  AS "Win %",
    ROUND(AVG(hold_days)::numeric, 0)                                AS "Avg Days"
FROM closed_trades
GROUP BY strategy
ORDER BY SUM(realized_pnl) DESC
"""

S["monthly_pnl"] = """
SELECT
    TO_CHAR(DATE_TRUNC('month', close_date), 'Mon YYYY')  AS "Month",
    ROUND(SUM(realized_pnl)::numeric, 0)                 AS "Monthly P&L ($)",
    ROUND(
        SUM(SUM(realized_pnl)) OVER (
            ORDER BY DATE_TRUNC('month', close_date)
        )::numeric, 0
    )                                                      AS "Cumulative ($)"
FROM closed_trades
GROUP BY DATE_TRUNC('month', close_date)
ORDER BY DATE_TRUNC('month', close_date)
"""

S["pnl_by_strategy"] = """
SELECT
    strategy                                 AS "Strategy",
    ROUND(SUM(realized_pnl)::numeric, 0)   AS "Total P&L ($)",
    COUNT(*)                                 AS "Trades",
    ROUND(
        100.0 * COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)
        / NULLIF(COUNT(*), 0)::numeric, 0
    )                                         AS "Win %"
FROM closed_trades
GROUP BY strategy
ORDER BY SUM(realized_pnl) DESC
"""

S["ytd_pnl"] = """
SELECT ROUND(SUM(realized_pnl)::numeric, 0) AS "YTD Realized P&L ($)"
FROM closed_trades
WHERE close_date >= DATE_TRUNC('year', CURRENT_DATE)
"""

S["total_trades"] = """
SELECT COUNT(*) AS "Total Closed Trades"
FROM closed_trades
"""

S["best_strategy"] = """
SELECT strategy AS "Best Strategy (P&L)"
FROM closed_trades
GROUP BY strategy
ORDER BY SUM(realized_pnl) DESC
LIMIT 1
"""

# ── Section 4: WHEEL INCOME ───────────────────────────────────────────────────

S["wheel_total_premium"] = """
SELECT ROUND(SUM(realized_pnl)::numeric, 0) AS "Total Wheel Premium ($)"
FROM closed_trades
WHERE strategy IN ('WheelSP', 'WheelSC')
"""

S["wheel_win_rate"] = """
SELECT ROUND(
    100.0 * COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)
    / NULLIF(COUNT(*), 0)::numeric, 1
) AS "Wheel Win Rate (%)"
FROM closed_trades
WHERE strategy IN ('WheelSP', 'WheelSC')
"""

S["wheel_avg_hold"] = """
SELECT ROUND(AVG(hold_days)::numeric, 1) AS "Avg Hold Days"
FROM closed_trades
WHERE strategy IN ('WheelSP', 'WheelSC')
  AND hold_days IS NOT NULL
"""

S["wheel_total_trades"] = """
SELECT COUNT(*) AS "Wheel Trades"
FROM closed_trades
WHERE strategy IN ('WheelSP', 'WheelSC')
"""

S["wheel_monthly"] = """
SELECT
    TO_CHAR(DATE_TRUNC('month', close_date), 'Mon YYYY')  AS "Month",
    strategy                                               AS "Type",
    ROUND(SUM(realized_pnl)::numeric, 0)                 AS "Premium ($)"
FROM closed_trades
WHERE strategy IN ('WheelSP', 'WheelSC')
GROUP BY DATE_TRUNC('month', close_date), strategy
ORDER BY DATE_TRUNC('month', close_date), strategy
"""

S["wheel_open"] = """
SELECT
    p.underlying                                               AS "Underlying",
    p.structure                                                AS "Structure",
    ps.qty                                                     AS "Qty",
    ROUND(ps.cost_basis::numeric, 0)                          AS "Cost ($)",
    ROUND(ps.current_value::numeric, 0)                       AS "Value ($)",
    ROUND(ps.gain_pct::numeric, 1)                            AS "Gain %",
    COALESCE(array_to_string(ps.flags, ' | '), '')            AS "Flags",
    COALESCE(ps.notes, '')                                     AS "Notes"
FROM position_snapshots ps
JOIN positions p ON p.id = ps.position_id
WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
  AND p.strategy IN ('WheelSP', 'WheelSC')
ORDER BY p.underlying
"""

S["wheel_by_underlying"] = """
SELECT
    underlying                               AS "Underlying",
    COUNT(*)                                 AS "Trades",
    ROUND(SUM(realized_pnl)::numeric, 0)   AS "Total Premium ($)",
    ROUND(AVG(gain_pct)::numeric, 1)         AS "Avg Gain %",
    ROUND(AVG(hold_days)::numeric, 0)        AS "Avg Days",
    ROUND(
        100.0 * COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)
        / NULLIF(COUNT(*), 0)::numeric, 0
    )                                         AS "Win %"
FROM closed_trades
WHERE strategy IN ('WheelSP', 'WheelSC')
GROUP BY underlying
ORDER BY SUM(realized_pnl) DESC
"""

# ── Section 5: RISK & COMPLIANCE ─────────────────────────────────────────────

S["deployment_vs_band"] = """
SELECT
    date            AS "Date",
    deployed_pct    AS "Deployed %",
    band_lo         AS "Band Low",
    band_hi         AS "Band High",
    eff_lev * 100   AS "Eff Lev %"
FROM daily_briefings
ORDER BY date
"""

S["oversized_positions"] = """
SELECT
    p.underlying                           AS "Ticker",
    p.strategy                             AS "Strategy",
    ROUND(ps.pct_nav::numeric, 1)         AS "% NAV",
    CASE
        WHEN p.strategy = 'Thematic'
             AND ps.pct_nav > 2  THEN 'Over 2% (Thematic cap)'
        WHEN p.strategy IN ('LEAP','LDS','2x-ETF')
             AND ps.pct_nav > 4  THEN 'Over 4% cap'
        ELSE 'OK'
    END                                    AS "Cap Status"
FROM position_snapshots ps
JOIN positions p ON p.id = ps.position_id
WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
  AND p.strategy NOT IN ('cash', 'WheelSP', 'WheelSC')
  AND (
        (p.strategy = 'Thematic'                AND ps.pct_nav > 2) OR
        (p.strategy IN ('LEAP','LDS','2x-ETF') AND ps.pct_nav > 4)
  )
ORDER BY ps.pct_nav DESC
"""

S["eff_lev_history"] = """
SELECT
    date    AS "Date",
    eff_lev AS "Eff Leverage"
FROM daily_briefings
ORDER BY date
"""

S["flags_trend"] = """
SELECT
    b.date       AS "Date",
    f.flag_type  AS "Flag Type",
    COUNT(*)     AS "Count"
FROM daily_flags f
JOIN daily_briefings b ON b.id = f.briefing_id
GROUP BY b.date, f.flag_type
ORDER BY b.date, f.flag_type
"""


# ── CARD CREATION LIST ────────────────────────────────────────────────────────

CARDS = [
    # key,                   display,   name
    ("nav",                  "scalar",  "NAV"),
    ("deployed_pct",         "scalar",  "Deployed %"),
    ("eff_lev",              "scalar",  "Eff Leverage"),
    ("free_capital",         "scalar",  "Free Capital"),
    ("decisions",            "table",   "Today's Decisions"),
    ("flags",                "table",   "Active Flags"),
    ("open_positions",       "table",   "Open Positions"),
    ("allocation",           "pie",     "Strategy Allocation"),
    ("nav_history",          "line",    "NAV History"),
    ("deployed_history",     "line",    "Deployed % vs Band"),
    ("strategy_scorecard",   "table",   "Strategy Scorecard"),
    ("monthly_pnl",          "bar",     "Monthly Realized P&L"),
    ("pnl_by_strategy",      "bar",     "P&L by Strategy"),
    ("ytd_pnl",              "scalar",  "YTD Realized P&L"),
    ("total_trades",         "scalar",  "Total Closed Trades"),
    ("best_strategy",        "scalar",  "Best Strategy"),
    ("wheel_total_premium",  "scalar",  "Wheel Total Premium"),
    ("wheel_win_rate",       "scalar",  "Wheel Win Rate"),
    ("wheel_avg_hold",       "scalar",  "Wheel Avg Hold Days"),
    ("wheel_total_trades",   "scalar",  "Wheel Trade Count"),
    ("wheel_monthly",        "bar",     "Monthly Wheel Income"),
    ("wheel_open",           "table",   "Active Wheel Positions"),
    ("wheel_by_underlying",  "table",   "Wheel Performance by Underlying"),
    ("deployment_vs_band",   "line",    "Deployment vs Band History"),
    ("oversized_positions",  "table",   "Oversized Positions"),
    ("eff_lev_history",      "line",    "Effective Leverage History"),
    ("flags_trend",          "bar",     "Flag Activity (Daily)"),
]


def build(reuse_dashboard=None):
    """
    Build the Trading Insights dashboard.
    If reuse_dashboard is a dashboard ID, populate that existing dashboard.
    Otherwise create cards + a new dashboard.
    """
    print("Building Trading Insights dashboard...\n")

    # 1 ── Create all cards
    print("Step 1: Creating cards...")
    ids = {}
    for key, display, name in CARDS:
        print(f"  {name} ({display})")
        c = card(name, S[key], display)
        ids[key] = c["id"]

    # 1b ── Apply conditional row formatting to the Flags card
    print("  Applying flag row colors...")
    mb("put", f"/card/{ids['flags']}", {
        "visualization_settings": {
            "table.column_formatting": [
                {"columns": ["Type"], "type": "single", "operator": "=",
                 "value": "HARVEST",      "color": "#74BF4B", "highlight_row": True},
                {"columns": ["Type"], "type": "single", "operator": "=",
                 "value": "TRIM",         "color": "#F9CF48", "highlight_row": True},
                {"columns": ["Type"], "type": "single", "operator": "=",
                 "value": "THESIS-CHECK", "color": "#F9CF48", "highlight_row": True},
                {"columns": ["Type"], "type": "single", "operator": "=",
                 "value": "UNDERWATER",   "color": "#EF8C8C", "highlight_row": True},
            ]
        }
    })

    # 2 ── Create or reuse dashboard
    if reuse_dashboard:
        did = reuse_dashboard
        print(f"\nStep 2: Reusing dashboard id={did}")
    else:
        print("\nStep 2: Creating dashboard...")
        dash = mb("post", "/dashboard", {"name": "Trading Insights"})
        did = dash["id"]
        print(f"  id={did}")

    # 3 ── Build dashcard layout
    print("\nStep 3: Building layout...")

    # ── SECTION 1: TODAY'S BRIEF ──────────────────────────────────────────────
    heading("TODAY'S BRIEF",              row=0,  col=0, sx=24, sy=1)

    # KPI row: NAV · Deployed% · Eff Lev · Free Capital
    place(ids["nav"],           row=1, col=0,  sx=6, sy=4)
    place(ids["deployed_pct"],  row=1, col=6,  sx=6, sy=4)
    place(ids["eff_lev"],       row=1, col=12, sx=6, sy=4)
    place(ids["free_capital"],  row=1, col=18, sx=6, sy=4)

    # Today's Decisions — full width
    place(ids["decisions"],     row=5,  col=0, sx=24, sy=9)

    # Active Flags — full width, row colors set on the card itself
    place(ids["flags"],         row=14, col=0, sx=24, sy=9)

    # ── SECTION 2: PORTFOLIO ─────────────────────────────────────────────────
    heading("PORTFOLIO",                  row=23, col=0, sx=24, sy=1)

    # Open positions table + allocation pie
    place(ids["open_positions"], row=24, col=0,  sx=17, sy=10)
    place(ids["allocation"],     row=24, col=17, sx=7,  sy=10)

    # NAV history + Deployed vs Band
    place(ids["nav_history"],       row=34, col=0,  sx=12, sy=8)
    place(ids["deployed_history"],  row=34, col=12, sx=12, sy=8)

    # ── SECTION 3: ANALYTICS ─────────────────────────────────────────────────
    heading("ANALYTICS",                  row=42, col=0, sx=24, sy=1)

    # Analytics KPI row
    place(ids["ytd_pnl"],       row=43, col=0,  sx=8, sy=4)
    place(ids["total_trades"],  row=43, col=8,  sx=8, sy=4)
    place(ids["best_strategy"], row=43, col=16, sx=8, sy=4)

    # Scorecard + Monthly P&L
    place(ids["strategy_scorecard"], row=47, col=0,  sx=10, sy=10)
    place(ids["monthly_pnl"],        row=47, col=10, sx=14, sy=10)

    # P&L by strategy bar
    place(ids["pnl_by_strategy"],    row=57, col=0,  sx=24, sy=8)

    # ── SECTION 4: WHEEL INCOME ───────────────────────────────────────────────
    heading("WHEEL INCOME",               row=65, col=0, sx=24, sy=1)

    # Wheel KPI row
    place(ids["wheel_total_premium"], row=66, col=0,  sx=6, sy=4)
    place(ids["wheel_win_rate"],      row=66, col=6,  sx=6, sy=4)
    place(ids["wheel_avg_hold"],      row=66, col=12, sx=6, sy=4)
    place(ids["wheel_total_trades"],  row=66, col=18, sx=6, sy=4)

    # Monthly wheel income bar + open positions + by underlying
    place(ids["wheel_monthly"],       row=70, col=0,  sx=24, sy=9)
    place(ids["wheel_open"],          row=79, col=0,  sx=14, sy=8)
    place(ids["wheel_by_underlying"], row=79, col=14, sx=10, sy=8)

    # ── SECTION 5: RISK & COMPLIANCE ─────────────────────────────────────────
    heading("RISK & COMPLIANCE",          row=87, col=0, sx=24, sy=1)

    place(ids["deployment_vs_band"],   row=88, col=0,  sx=16, sy=9)
    place(ids["oversized_positions"],  row=88, col=16, sx=8,  sy=9)

    place(ids["eff_lev_history"],      row=97, col=0,  sx=12, sy=8)
    place(ids["flags_trend"],          row=97, col=12, sx=12, sy=8)

    # 4 ── Push all dashcards to the dashboard in one PUT
    print(f"\nStep 4: Flushing {len(_dashcards)} cards to dashboard {did}...")
    flush_to_dashboard(did)

    print(f"\nDone!\nDashboard: http://139.99.197.93/dashboard/{did}")
    return did


if __name__ == "__main__":
    import sys as _sys
    # Pass an existing dashboard ID to repopulate it: python3 build_dashboard.py 4
    existing = int(_sys.argv[1]) if len(_sys.argv) > 1 else None
    build(reuse_dashboard=existing)
