from fastapi import APIRouter
from app.db import query, query_one

router = APIRouter()


@router.get("/summary")
def summary():
    return query_one("""
        SELECT
            date,
            nav,
            ROUND(nav - cash_value - sgov_value, 0)                                       AS deployed,
            ROUND(100.0 * (nav - cash_value - sgov_value) / NULLIF(nav, 0), 1)            AS deployed_pct
        FROM account_snapshots
        WHERE account_id = 1
        ORDER BY date DESC LIMIT 1
    """)


@router.get("/pnl")
def pnl():
    rows = query("""
        SELECT
            ROUND(SUM(realized_pnl) FILTER (WHERE EXTRACT(YEAR  FROM close_date) = EXTRACT(YEAR  FROM CURRENT_DATE))::numeric, 0)  AS ytd,
            ROUND(SUM(realized_pnl) FILTER (WHERE EXTRACT(YEAR  FROM close_date) = EXTRACT(YEAR  FROM CURRENT_DATE)
                                                AND EXTRACT(MONTH FROM close_date) = EXTRACT(MONTH FROM CURRENT_DATE))::numeric, 0) AS mtd,
            ROUND(SUM(realized_pnl) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year')::numeric, 0)                     AS one_year,
            COUNT(*)               FILTER (WHERE EXTRACT(YEAR  FROM close_date) = EXTRACT(YEAR  FROM CURRENT_DATE))                AS ytd_trades
        FROM closed_trades
        WHERE account_id = 1
    """)
    return rows[0] if rows else {}


@router.get("/positions")
def positions():
    return query("""
        SELECT
            p.symbol,
            p.underlying,
            p.strategy,
            p.theme,
            ROUND(ps.qty::numeric, 0)           AS qty,
            ROUND(ps.cost_basis::numeric, 0)    AS cost,
            ROUND(ps.current_value::numeric, 0) AS value,
            ROUND(ps.gain_pct::numeric, 1)      AS gain_pct,
            ROUND(ps.pct_nav::numeric, 1)       AS pct_nav,
            pn.note
        FROM position_snapshots ps
        JOIN positions p ON p.id = ps.position_id
        LEFT JOIN position_notes pn
               ON pn.account_id = p.account_id
              AND pn.underlying = p.underlying
              AND pn.active = TRUE
              AND (pn.snooze_until IS NULL OR pn.snooze_until >= CURRENT_DATE)
        WHERE ps.snapshot_date = (SELECT MAX(snapshot_date) FROM position_snapshots)
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
