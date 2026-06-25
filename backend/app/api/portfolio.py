from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from app.db import query, query_one, execute

router = APIRouter()


@router.get("/summary")
def summary():
    return query_one("""
        SELECT
            a.snapshot_date                                                              AS date,
            a.nav,
            ROUND(a.nav - a.cash - a.sgov, 0)                                          AS deployed,
            ROUND(100.0 * (a.nav - a.cash - a.sgov) / NULLIF(a.nav, 0), 1)            AS deployed_pct,
            ROUND(a.cash + a.sgov, 0)                                                   AS total_cash,
            ROUND(a.eff_leverage::numeric, 2)                                           AS eff_leverage,
            a.updated_at                                                                 AS last_updated,
            a.daily_pnl,
            ROUND(
                100.0 * a.daily_pnl / NULLIF(a.nav - a.daily_pnl, 0), 2
            )                                                                            AS daily_pnl_pct
        FROM account_snapshots a
        WHERE a.account_id = 1
        ORDER BY a.snapshot_date DESC LIMIT 1
    """)


@router.get("/pnl")
def pnl():
    rows = query("""
        SELECT
            ROUND(SUM(realized_pnl) FILTER (WHERE EXTRACT(YEAR  FROM close_date) = EXTRACT(YEAR  FROM CURRENT_DATE)), 0)  AS ytd,
            ROUND(SUM(realized_pnl) FILTER (WHERE EXTRACT(YEAR  FROM close_date) = EXTRACT(YEAR  FROM CURRENT_DATE)
                                                AND EXTRACT(MONTH FROM close_date) = EXTRACT(MONTH FROM CURRENT_DATE)), 0) AS mtd,
            ROUND(SUM(realized_pnl) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year'), 0)                     AS one_year,
            COUNT(*)               FILTER (WHERE EXTRACT(YEAR  FROM close_date) = EXTRACT(YEAR  FROM CURRENT_DATE))       AS ytd_trades
        FROM closed_trades
        WHERE account_id = 1
    """)
    return rows[0] if rows else {}


@router.get("/positions")
def positions():
    return query("""
        WITH today    AS (SELECT MAX(snapshot_date) AS d FROM position_snapshots),
             prev_day AS (SELECT MAX(snapshot_date) AS d FROM position_snapshots
                          WHERE snapshot_date < (SELECT d FROM today)),
             prev_wk  AS (SELECT MAX(snapshot_date) AS d FROM position_snapshots
                          WHERE snapshot_date <= (SELECT d FROM today) - INTERVAL '5 days')
        SELECT
            p.symbol,
            p.underlying,
            p.strategy,
            p.theme,
            ROUND(ps.qty::numeric, 0)                                       AS qty,
            ROUND(ps.cost_basis::numeric, 0)                                AS cost,
            ROUND(ps.cost_basis / NULLIF(ps.qty, 0), 2)                    AS avg_price,
            ROUND(ps.current_value::numeric, 0)                             AS value,
            ROUND(ps.gain_pct::numeric, 1)                                  AS gain_pct,
            ROUND(ps.pct_nav::numeric, 1)                                   AS pct_nav,
            ROUND((ps.gain_pct - ps_p.gain_pct)::numeric, 1)               AS daily_pp,
            ROUND((ps.current_value - ps_p.current_value)::numeric, 0)     AS daily_usd,
            ROUND((ps.gain_pct - ps_w.gain_pct)::numeric, 1)               AS weekly_pp,
            ps.notes                                                         AS csv_note,
            ps.ai_note,
            ps.flags,
            p.assignment_price,
            pn.note,
            pn.suppress_flags
        FROM position_snapshots ps
        JOIN positions p ON p.id = ps.position_id
        LEFT JOIN position_snapshots ps_p
               ON ps_p.position_id   = ps.position_id
              AND ps_p.snapshot_date  = (SELECT d FROM prev_day)
        LEFT JOIN position_snapshots ps_w
               ON ps_w.position_id   = ps.position_id
              AND ps_w.snapshot_date  = (SELECT d FROM prev_wk)
        LEFT JOIN position_notes pn
               ON pn.account_id = p.account_id
              AND pn.underlying = p.underlying
              AND pn.active = TRUE
              AND (pn.snooze_until IS NULL OR pn.snooze_until >= CURRENT_DATE)
        WHERE ps.snapshot_date = (SELECT d FROM today)
          AND p.strategy <> 'cash'
          AND p.closed_date IS NULL
        ORDER BY ps.pct_nav DESC NULLS LAST
    """)


@router.get("/flags")
def flags():
    return query("""
        SELECT
            f.flag_type  AS type,
            f.symbol     AS ticker,
            f.note,
            pn.note      AS user_note
        FROM daily_flags f
        JOIN daily_briefings b ON b.id = f.briefing_id
        LEFT JOIN position_notes pn
               ON pn.account_id = b.account_id
              AND pn.underlying = f.symbol
              AND pn.active = TRUE
              AND (pn.snooze_until IS NULL OR pn.snooze_until >= CURRENT_DATE)
        WHERE b.date = (SELECT MAX(date) FROM daily_briefings)
        ORDER BY
            CASE f.flag_type
                WHEN 'UNDERWATER'    THEN 1
                WHEN 'WHEEL-STUCK'   THEN 2
                WHEN 'WHEEL-AT-RISK' THEN 3
                WHEN 'THESIS-CHECK'  THEN 4
                WHEN 'HARVEST'       THEN 5
                WHEN 'TRIM'          THEN 6
                ELSE 7
            END, f.symbol
    """)


@router.get("/wheel")
def wheel():
    return query("""
        SELECT
            p.underlying,
            p.symbol,
            p.strategy,
            ROUND(ps.cost_basis::numeric, 0)    AS cost,
            ROUND(ps.current_value::numeric, 0) AS value,
            ROUND(ps.gain_pct::numeric, 1)      AS gain_pct,
            p.assignment_price
        FROM position_snapshots ps
        JOIN positions p ON p.id = ps.position_id
        WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
          AND p.strategy IN ('WheelSP', 'WheelSC')
          AND p.closed_date IS NULL
        ORDER BY p.strategy, p.underlying
    """)


@router.get("/wheel-stats")
def wheel_stats():
    """Assignment risk + remaining OTM premium for the wheel book."""
    return query_one("""
        SELECT
            -- Capital required if every short put is assigned (strike × 100 × |qty|)
            ROUND(COALESCE(SUM(
                CASE WHEN p.strategy = 'WheelSP' AND p.symbol ~ '.*_[0-9.]+P$' THEN
                    REGEXP_REPLACE(p.symbol, '.*_([0-9.]+)P$', '\\1')::numeric
                    * 100 * ABS(ps.qty::numeric)
                END
            ), 0), 0)                       AS assignment_risk,

            -- Original credit received from open short options (what stays if they expire OTM)
            ROUND(COALESCE(SUM(
                CASE WHEN p.strategy IN ('WheelSP', 'WheelSC')
                          AND p.symbol NOT LIKE '%%STK%%' THEN
                    ps.cost_basis::numeric
                END
            ), 0), 0)                       AS otm_premium

        FROM position_snapshots ps
        JOIN positions p ON p.id = ps.position_id
        WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
          AND p.strategy IN ('WheelSP', 'WheelSC')
          AND p.closed_date IS NULL
    """)


# ── Briefings ────────────────────────────────────────────────────────────────

@router.get("/briefing/latest")
def latest_briefing():
    return query_one("""
        SELECT date, nav, deployed_pct, eff_lev, wheel_cover, commentary,
               market_summary, wheel_section, watchlist, briefing_md
        FROM daily_briefings
        WHERE account_id = 1
        ORDER BY date DESC LIMIT 1
    """)


@router.get("/briefings")
def briefings_list():
    return query("""
        SELECT date, nav, deployed_pct, eff_lev
        FROM daily_briefings
        WHERE account_id = 1
        ORDER BY date DESC LIMIT 30
    """)


@router.get("/briefing/{date}")
def briefing_by_date(date: str):
    return query_one("""
        SELECT date, nav, deployed_pct, eff_lev, wheel_cover, commentary,
               market_summary, wheel_section, watchlist, briefing_md
        FROM daily_briefings
        WHERE account_id = 1 AND date = %s
    """, [date])


# ── Position notes ────────────────────────────────────────────────────────────

class NoteBody(BaseModel):
    note: str
    suppress_flags: list[str] = []
    snooze_until: Optional[str] = None


@router.post("/positions/{underlying}/note")
def upsert_position_note(underlying: str, body: NoteBody):
    """Create or update an acknowledgement note for a position (by underlying)."""
    snooze = body.snooze_until or None
    execute("""
        INSERT INTO position_notes (account_id, underlying, note, suppress_flags, snooze_until, active)
        VALUES (1, %s, %s, %s, %s, TRUE)
        ON CONFLICT (account_id, underlying, COALESCE(strategy, ''))
        DO UPDATE SET
            note           = EXCLUDED.note,
            suppress_flags = EXCLUDED.suppress_flags,
            snooze_until   = EXCLUDED.snooze_until,
            active         = TRUE,
            updated_at     = NOW()
    """, [underlying, body.note, body.suppress_flags, snooze])
    return {"ok": True}


@router.delete("/positions/{underlying}/note")
def delete_position_note(underlying: str):
    """Deactivate (soft-delete) the acknowledgement note for a position."""
    execute("""
        UPDATE position_notes
        SET active = FALSE, updated_at = NOW()
        WHERE account_id = 1 AND underlying = %s AND active = TRUE
    """, [underlying])
    return {"ok": True}
