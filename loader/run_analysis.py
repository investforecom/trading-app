"""
Layer 2 — weekly portfolio behaviour analysis.

Reads existing tables (never modifies them).
Writes to analysis_runs + insights.
Called by sync.sh on Saturdays; can be run manually any time.

Env vars (same as loader):
    PGHOST, PGDATABASE, PGUSER, PGPASSWORD
    DISCORD_WEBHOOK_URL  (optional — skip Discord if unset)
"""
import json
import os
from datetime import date
from decimal import Decimal

import requests as _requests

from db import transaction, fetch_all, fetch_one

ACCOUNT_ID = 1
MIN_TRADES = 3
MIN_FLAG_EVENTS = 2

SEV_ORDER = {"ACTION": 0, "WATCH": 1, "INFO": 2}

DISCORD_WEBHOOK    = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
METABASE_URL       = os.environ.get("METABASE_URL", "http://127.0.0.1:80")
METABASE_TOKEN     = os.environ.get("METABASE_TOKEN", "").strip()
WEEKLY_DASHBOARD_ID = 5
NARRATIVE_DASHCARD_ID = 92

# Strategies where the thesis is multi-year; harvest only at 80%+ and let Thematic run
LONG_THESIS_STRATEGIES = ("LEAP", "LDS", "2x-ETF")
HARVEST_THRESHOLD_LONG = 80.0   # % gain — LEAP/LDS/2x-ETF
# Thematic: no harvest flag; instead flag DCA opportunity when below cost and under 2% cap


def _suppressed_underlyings(cur, flag_type: str) -> set[str]:
    """Return underlyings where flag_type is in suppress_flags and snooze hasn't expired."""
    rows = _all(cur, """
        SELECT underlying FROM position_notes
        WHERE account_id = %s
          AND active = TRUE
          AND %s = ANY(suppress_flags)
          AND (snooze_until IS NULL OR snooze_until >= CURRENT_DATE)
    """, (ACCOUNT_ID, flag_type))
    return {r["underlying"] for r in rows}


def _jsonable(obj):
    """Recursively convert Decimal → float so metric_json is serialisable."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


# ── helpers ──────────────────────────────────────────────────────────────────

def _all(cur, sql, params=None):
    return fetch_all(cur, sql, params or ())

def _one(cur, sql, params=None):
    return fetch_one(cur, sql, params or ())


# ── 1. Strategy performance (rolling 90 days) ────────────────────────────────

def _strategy_performance(cur):
    rows = _all(cur, """
        SELECT
            strategy::text                                             AS strategy,
            COUNT(*)                                                   AS trades,
            ROUND(100.0 * COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)
                  / NULLIF(COUNT(*),0)::numeric, 1)                   AS win_rate,
            ROUND(AVG(gain_pct)::numeric, 1)                          AS avg_gain,
            ROUND(SUM(realized_pnl)::numeric, 0)                      AS total_pnl
        FROM closed_trades
        WHERE close_date >= CURRENT_DATE - INTERVAL '90 days'
        GROUP BY strategy
        ORDER BY total_pnl ASC
    """)

    insights = []
    for r in rows:
        if r["trades"] < MIN_TRADES:
            continue
        strat = r["strategy"]

        # LDS/LEAP/2x-ETF: positively skewed — require BOTH low win rate AND negative total P&L
        if strat in LONG_THESIS_STRATEGIES:
            if r["win_rate"] < 40 and r["total_pnl"] < 0:
                sev = "ACTION"
            elif r["win_rate"] < 45 and r["total_pnl"] < 0:
                sev = "WATCH"
            else:
                continue
        elif strat == "Thematic":
            # Thematic: multi-year hold — only flag if avg gain < -15% (deep underwater)
            if r["avg_gain"] < -15 and r["total_pnl"] < -1000:
                sev = "WATCH"
            else:
                continue
        else:
            if r["win_rate"] < 40 or r["avg_gain"] < -5:
                sev = "ACTION"
            elif r["win_rate"] < 55:
                sev = "WATCH"
            else:
                continue

        insights.append({
            "category": "STRATEGY",
            "severity": sev,
            "title": f"{strat}: {r['win_rate']}% win rate, avg {r['avg_gain']:+.1f}% (90d)",
            "body": (
                f"{strat} last 90 days — {r['trades']} trades, "
                f"{r['win_rate']}% win rate, avg {r['avg_gain']:+.1f}% per trade, "
                f"total P&L ${r['total_pnl']:+,.0f}."
            ),
            "metric_json": dict(r),
        })
    return insights


# ── 2. Monthly P&L trend ─────────────────────────────────────────────────────

def _pnl_trend(cur):
    rows = _all(cur, """
        SELECT
            TO_CHAR(DATE_TRUNC('month', close_date), 'Mon') AS month,
            ROUND(SUM(realized_pnl)::numeric, 0)            AS pnl
        FROM closed_trades
        WHERE close_date >= DATE_TRUNC('year', CURRENT_DATE)
        GROUP BY DATE_TRUNC('month', close_date)
        ORDER BY DATE_TRUNC('month', close_date)
    """)

    if len(rows) < 3:
        return []

    last3 = rows[-3:]
    pnls = [r["pnl"] for r in last3]
    summary = ", ".join(f"{r['month']} ${r['pnl']:+,.0f}" for r in last3)

    if pnls[2] < pnls[1] < pnls[0]:
        return [{
            "category": "TREND",
            "severity": "WATCH",
            "title": "P&L declining — 3 consecutive months",
            "body": (
                f"Three consecutive months of declining P&L: {summary}. "
                f"Review strategy mix and entry discipline."
            ),
            "metric_json": {"months": [dict(r) for r in last3]},
        }]
    if pnls[2] > pnls[1] > pnls[0]:
        return [{
            "category": "TREND",
            "severity": "INFO",
            "title": "P&L improving — 3 consecutive months",
            "body": (
                f"Positive momentum: {summary}. "
                f"Current approach working — maintain discipline."
            ),
            "metric_json": {"months": [dict(r) for r in last3]},
        }]
    return []


# ── 3. Hold time by strategy ─────────────────────────────────────────────────

def _hold_time(cur):
    # Expected avg-hold ceilings (days). Strategies without a ceiling are skipped.
    ceilings = {"WheelSP": 45, "WheelSC": 45, "SWING": 90}

    rows = _all(cur, """
        SELECT
            strategy::text                    AS strategy,
            COUNT(*)                          AS trades,
            ROUND(AVG(hold_days)::numeric, 0) AS avg_hold,
            ROUND(MAX(hold_days)::numeric, 0) AS max_hold
        FROM closed_trades
        WHERE close_date >= CURRENT_DATE - INTERVAL '1 year'
          AND hold_days IS NOT NULL
        GROUP BY strategy
        HAVING COUNT(*) >= %(min)s
    """, {"min": MIN_TRADES})

    insights = []
    for r in rows:
        ceiling = ceilings.get(r["strategy"])
        if ceiling and r["avg_hold"] > ceiling:
            insights.append({
                "category": "BEHAVIOR",
                "severity": "WATCH",
                "title": f"{r['strategy']}: avg hold {r['avg_hold']}d — ceiling ~{ceiling}d",
                "body": (
                    f"{r['strategy']} positions held avg {r['avg_hold']} days "
                    f"vs expected max ~{ceiling}d. Longest single hold: {r['max_hold']}d. "
                    f"Review exit discipline for this strategy."
                ),
                "metric_json": dict(r),
            })
    return insights


# ── 4. Wheel quality by underlying ───────────────────────────────────────────

def _wheel_underlying(cur):
    rows = _all(cur, """
        SELECT
            underlying,
            COUNT(*)                                                    AS trades,
            ROUND(SUM(realized_pnl)::numeric, 0)                      AS total_pnl,
            ROUND(AVG(gain_pct)::numeric, 1)                           AS avg_gain,
            ROUND(100.0 * COUNT(CASE WHEN realized_pnl < 0 THEN 1 END)
                  / NULLIF(COUNT(*),0)::numeric, 0)                    AS loss_rate
        FROM closed_trades
        WHERE strategy IN ('WheelSP','WheelSC')
          AND close_date >= CURRENT_DATE - INTERVAL '1 year'
        GROUP BY underlying
        HAVING COUNT(*) >= %(min)s
        ORDER BY total_pnl ASC
    """, {"min": MIN_TRADES})

    insights = []
    for r in rows:
        if r["total_pnl"] >= 0 and r["loss_rate"] < 50:
            continue
        sev = "ACTION" if r["total_pnl"] < -500 else "WATCH"
        insights.append({
            "category": "WHEEL",
            "severity": sev,
            "title": f"Wheel {r['underlying']}: ${r['total_pnl']:+,.0f} ({r['loss_rate']}% loss rate, 1y)",
            "body": (
                f"{r['underlying']} wheel performance: {r['trades']} trades, "
                f"${r['total_pnl']:+,.0f} total, {r['loss_rate']}% loss rate, "
                f"avg {r['avg_gain']:+.1f}%. Consider repricing or avoiding."
            ),
            "metric_json": dict(r),
        })
    return insights


# ── 4b. Thematic DCA opportunities ───────────────────────────────────────────

def _thematic_dca(cur):
    """Flag Thematic positions that are below cost AND under the 2% cap — DCA candidates."""
    suppressed = _suppressed_underlyings(cur, "DCA-CANDIDATE")
    nav_row = _one(cur, "SELECT nav FROM daily_briefings ORDER BY date DESC LIMIT 1")
    if not nav_row:
        return []
    nav = float(nav_row["nav"])

    rows = _all(cur, """
        SELECT
            p.underlying,
            ROUND(ps.cost_basis::numeric, 0)                          AS cost,
            ROUND(ps.current_value::numeric, 0)                       AS value,
            ROUND(ps.gain_pct::numeric, 1)                            AS gain_pct,
            ROUND(100.0 * ps.cost_basis / %(nav)s, 1)                AS pct_nav_cost
        FROM position_snapshots ps
        JOIN positions p ON p.id = ps.position_id
        WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
          AND p.strategy = 'Thematic'
          AND p.closed_date IS NULL
          AND ps.gain_pct < 0
          AND 100.0 * ps.cost_basis / %(nav)s < 2.0
        ORDER BY ps.gain_pct ASC
    """, {"nav": nav})

    insights = []
    for r in rows:
        if r["underlying"] in suppressed:
            continue
        insights.append({
            "category": "THEMATIC",
            "severity": "INFO",
            "title": f"DCA candidate: {r['underlying']} ({r['gain_pct']:+.1f}%, {r['pct_nav_cost']}% of NAV)",
            "body": (
                f"{r['underlying']} Thematic position: {r['gain_pct']:+.1f}% unrealised, "
                f"cost ${r['cost']:,.0f} ({r['pct_nav_cost']}% of NAV vs 2.0% cap). "
                f"Room to DCA if thesis intact."
            ),
            "metric_json": dict(r),
        })
    return insights


# ── 5. Position sizing adherence ─────────────────────────────────────────────

def _sizing(cur):
    nav_row = _one(cur, "SELECT nav FROM daily_briefings ORDER BY date DESC LIMIT 1")
    if not nav_row:
        return []
    nav = float(nav_row["nav"])

    rows = _all(cur, """
        SELECT
            p.underlying,
            p.strategy::text                                           AS strategy,
            ROUND(ps.cost_basis::numeric, 0)                          AS cost,
            ROUND(100.0 * ps.cost_basis / %(nav)s, 1)                AS pct_nav,
            CASE
                WHEN p.strategy IN ('LEAP','LDS','2x-ETF') THEN 4.0
                WHEN p.strategy = 'Thematic'               THEN 2.5
            END                                                        AS limit_pct
        FROM position_snapshots ps
        JOIN positions p ON p.id = ps.position_id
        WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
          AND p.strategy IN ('LEAP','LDS','2x-ETF','Thematic')
          AND p.closed_date IS NULL
          AND (
            (p.strategy IN ('LEAP','LDS','2x-ETF') AND 100.0 * ps.cost_basis / %(nav)s > 4.0)
            OR
            (p.strategy = 'Thematic'               AND 100.0 * ps.cost_basis / %(nav)s > 2.5)
          )
        ORDER BY pct_nav DESC
    """, {"nav": nav})

    if not rows:
        return []

    names = ", ".join(
        f"{r['underlying']} ({r['pct_nav']}% vs {r['limit_pct']}% cap)"
        for r in rows
    )
    return [{
        "category": "SIZING",
        "severity": "ACTION" if len(rows) >= 3 else "WATCH",
        "title": f"{len(rows)} position(s) over cost-basis cap",
        "body": (
            f"Entry-size cap breach: {names}. "
            f"Trim on next strength — these positions carry outsized single-name risk."
        ),
        "metric_json": {"oversized": [dict(r) for r in rows], "nav": nav},
    }]


# ── 6. HARVEST flag response lag ─────────────────────────────────────────────

def _harvest_lag(cur):
    rows = _all(cur, """
        SELECT
            f.symbol,
            b.date                          AS flag_date,
            MIN(ct.close_date)              AS close_date,
            MIN(ct.close_date) - b.date     AS days_lag
        FROM daily_flags f
        JOIN daily_briefings b ON b.id = f.briefing_id
        JOIN closed_trades ct
             ON ct.underlying = f.symbol
            AND ct.close_date > b.date
            AND ct.close_date <= b.date + INTERVAL '21 days'
        WHERE f.flag_type = 'HARVEST'
          AND f.symbol ~ '^[A-Z][A-Z0-9]{0,9}$'
        GROUP BY f.symbol, b.date
        HAVING MIN(ct.close_date) IS NOT NULL
    """)

    if len(rows) < MIN_FLAG_EVENTS:
        return []

    avg_lag = sum(r["days_lag"] for r in rows) / len(rows)
    slow = sum(1 for r in rows if r["days_lag"] > 3)

    if avg_lag <= 3:
        return []

    return [{
        "category": "BEHAVIOR",
        "severity": "WATCH",
        "title": f"HARVEST actioned avg {avg_lag:.1f}d after flag",
        "body": (
            f"{len(rows)} HARVEST flag → close events: avg {avg_lag:.1f} day lag, "
            f"{slow} closed >3 days after flag. "
            f"Actioning within 1–2 days locks in gains before reversals."
        ),
        "metric_json": {"avg_lag_days": round(avg_lag, 1), "n": len(rows), "slow": slow},
    }]


# ── 7. UNDERWATER hold behaviour ─────────────────────────────────────────────

def _underwater_hold(cur):
    rows = _all(cur, """
        SELECT
            f.symbol,
            b.date                          AS flag_date,
            MIN(ct.close_date)              AS close_date,
            MIN(ct.close_date) - b.date     AS days_held_after
        FROM daily_flags f
        JOIN daily_briefings b ON b.id = f.briefing_id
        LEFT JOIN closed_trades ct
             ON ct.underlying = f.symbol
            AND ct.close_date > b.date
            AND ct.close_date <= b.date + INTERVAL '60 days'
        WHERE f.flag_type = 'UNDERWATER'
          AND f.symbol ~ '^[A-Z][A-Z0-9]{0,9}$'
        GROUP BY f.symbol, b.date
    """)

    if len(rows) < MIN_FLAG_EVENTS:
        return []

    still_open = [r for r in rows if r["close_date"] is None]
    if not still_open:
        return []

    names = ", ".join(r["symbol"] for r in still_open)
    return [{
        "category": "BEHAVIOR",
        "severity": "WATCH",
        "title": f"{len(still_open)} UNDERWATER position(s) still open",
        "body": (
            f"Positions flagged UNDERWATER with no close detected: {names}. "
            f"Verify thesis is still valid — holding through flags without a reason "
            f"is the most common source of oversized losses."
        ),
        "metric_json": {"symbols": [r["symbol"] for r in still_open]},
    }]


# ── orchestrator ─────────────────────────────────────────────────────────────

ANALYSES = [
    _strategy_performance,
    _pnl_trend,
    _hold_time,
    _wheel_underlying,
    _thematic_dca,
    _sizing,
    _harvest_lag,
    _underwater_hold,
]


def _build_narrative(insights: list[dict], run_date: date) -> str:
    """Plain-text narrative stored in analysis_runs.narrative."""
    actions = [i for i in insights if i["severity"] == "ACTION"]
    watches = [i for i in insights if i["severity"] == "WATCH"]
    infos   = [i for i in insights if i["severity"] == "INFO"]
    lines = [f"Weekly Analysis — {run_date.strftime('%d %b %Y')}",
             f"{len(actions)} action · {len(watches)} watch · {len(infos)} info", ""]
    if not insights:
        lines.append("All thresholds clear.")
    for sev, items in (("ACTION", actions), ("WATCH", watches), ("INFO", infos)):
        for i in items:
            lines.append(f"[{sev}] {i['category']}: {i['title']}")
            lines.append(f"  {i['body']}")
    return "\n".join(lines)


def _build_narrative_md(insights: list[dict], run_date: date) -> str:
    """Markdown for Metabase virtual Text card — renders as formatted summary."""
    actions = [i for i in insights if i["severity"] == "ACTION"]
    watches = [i for i in insights if i["severity"] == "WATCH"]
    infos   = [i for i in insights if i["severity"] == "INFO"]

    lines = [f"## Weekly Analysis — {run_date.strftime('%d %b %Y')}",
             ""]

    if not insights:
        lines += ["**All thresholds clear.** Nothing flagged this week.", ""]
        return "\n".join(lines)

    # Summary badge line
    parts = []
    if actions: parts.append(f"🔴 **{len(actions)} action item{'s' if len(actions)>1 else ''}**")
    if watches: parts.append(f"🟡 **{len(watches)} watch item{'s' if len(watches)>1 else ''}**")
    if infos:   parts.append(f"🟢 **{len(infos)} signal{'s' if len(infos)>1 else ''}**")
    lines += [" · ".join(parts), "", "---", ""]

    if actions:
        lines.append("### 🔴 Needs Attention")
        for i in actions:
            lines.append(f"**[{i['category']}]** {i['title']}")
            lines.append(f"> {i['body']}")
            lines.append("")

    if watches:
        lines.append("### 🟡 Monitoring")
        for i in watches:
            lines.append(f"**[{i['category']}]** {i['title']}")
            lines.append(f"> {i['body']}")
            lines.append("")

    if infos:
        lines.append("### 🟢 Signals & Opportunities")
        for i in infos:
            lines.append(f"**[{i['category']}]** {i['title']}")
            lines.append(f"> {i['body']}")
            lines.append("")

    return "\n".join(lines)


def _metabase_push_narrative(md: str) -> None:
    """Update the virtual Text card on the weekly dashboard with fresh markdown."""
    if not METABASE_TOKEN:
        return
    hdr = {"X-Metabase-Session": METABASE_TOKEN, "Content-Type": "application/json"}
    try:
        d = _requests.get(f"{METABASE_URL}/api/dashboard/{WEEKLY_DASHBOARD_ID}",
                          headers=hdr, timeout=10).json()
        updated = []
        for c in d["dashcards"]:
            entry = {k: c[k] for k in
                     ["id", "card_id", "row", "col", "size_x", "size_y",
                      "parameter_mappings", "visualization_settings", "series"]
                     if k in c}
            if c["id"] == NARRATIVE_DASHCARD_ID:
                vs = dict(entry.get("visualization_settings", {}))
                vs["text"] = md
                entry["visualization_settings"] = vs
            updated.append(entry)
        resp = _requests.put(f"{METABASE_URL}/api/dashboard/{WEEKLY_DASHBOARD_ID}",
                             headers=hdr, json={"dashcards": updated}, timeout=10)
        if resp.ok:
            print("  Metabase narrative card updated.")
        else:
            print(f"  Metabase update failed: {resp.status_code}")
    except Exception as exc:
        print(f"  Metabase narrative update skipped: {exc}")


def run(account_id: int = ACCOUNT_ID) -> list[dict]:
    all_insights = []

    with transaction() as cur:
        cur.execute("""
            INSERT INTO analysis_runs (account_id, run_date, run_type)
            VALUES (%s, CURRENT_DATE, 'weekly')
            ON CONFLICT (account_id, run_date) DO UPDATE SET run_type = 'weekly'
            RETURNING id
        """, (account_id,))
        run_id = cur.fetchone()["id"]

        cur.execute("DELETE FROM insights WHERE run_id = %s", (run_id,))

        for fn in ANALYSES:
            try:
                for ins in fn(cur):
                    cur.execute("""
                        INSERT INTO insights
                            (run_id, account_id, category, severity, title, body, metric_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        run_id, account_id,
                        ins["category"], ins["severity"],
                        ins["title"], ins["body"],
                        json.dumps(_jsonable(ins.get("metric_json"))),
                    ))
                    all_insights.append(ins)
            except Exception as exc:
                print(f"  [{fn.__name__}] skipped: {exc}")

    all_insights.sort(key=lambda x: SEV_ORDER.get(x["severity"], 9))

    run_date = date.today()
    narrative = _build_narrative(all_insights, run_date)
    with transaction() as cur:
        cur.execute(
            "UPDATE analysis_runs SET narrative = %s WHERE id = %s",
            (narrative, run_id),
        )

    _metabase_push_narrative(_build_narrative_md(all_insights, run_date))

    return all_insights


# ── Discord post ─────────────────────────────────────────────────────────────

def _discord_post(insights: list[dict], run_date: date) -> None:
    if not DISCORD_WEBHOOK:
        print("  DISCORD_WEBHOOK_URL not set — skipping Discord post")
        return

    sev_prefix = {"ACTION": "🔴", "WATCH": "🟡", "INFO": "🟢"}
    lines = [f"📊 **WEEKLY ANALYSIS** — {run_date}"]
    for ins in insights[:5]:   # cap at 5 to stay under 2000 chars
        prefix = sev_prefix.get(ins["severity"], "⚪")
        lines.append(f"{prefix} **{ins['category']}** · {ins['title']}")
        lines.append(f"  ↳ {ins['body']}")
    if not insights:
        lines.append("No issues flagged — all thresholds clear.")
    lines.append("http://139.99.197.93/dashboard/5-weekly")

    message = "\n".join(lines)
    if len(message) > 1900:
        message = "\n".join(lines[:6]) + "\n…\nhttp://139.99.197.93/dashboard/4"

    resp = _requests.post(
        DISCORD_WEBHOOK,
        json={"content": message},
        headers={"User-Agent": "curl/8.0"},
        timeout=10,
    )
    if resp.status_code == 204:
        print("  Discord OK")
    else:
        print(f"  Discord unexpected status {resp.status_code}: {resp.text[:200]}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    today = date.today()
    print(f"=== Weekly analysis {today} ===")
    insights = run()
    for ins in insights:
        print(f"[{ins['severity']:6s}] {ins['category']:10s} {ins['title']}")
        print(f"         {ins['body']}")
    if not insights:
        print("  No insights generated — all thresholds clear or insufficient data.")
    _discord_post(insights, today)
    print("=== done ===")
