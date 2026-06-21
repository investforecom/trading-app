from fastapi import APIRouter
from app.db import query

router = APIRouter()


@router.get("/scorecard")
def scorecard():
    return query("""
        SELECT
            strategy,
            COUNT(*) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year')        AS trades_1y,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE realized_pnl > 0 AND close_date >= CURRENT_DATE - INTERVAL '1 year')
                / NULLIF(COUNT(*) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year'), 0)
            , 0)                                                                            AS win_rate,
            ROUND(AVG(gain_pct) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year'), 1) AS avg_gain_pct,
            ROUND(SUM(realized_pnl) FILTER (WHERE EXTRACT(YEAR FROM close_date) = EXTRACT(YEAR FROM CURRENT_DATE)), 0) AS ytd_pnl,
            ROUND(SUM(realized_pnl) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year'), 0) AS pnl_1y
        FROM closed_trades
        WHERE account_id = 1 AND strategy IS NOT NULL
        GROUP BY strategy
        HAVING COUNT(*) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year') > 0
        ORDER BY pnl_1y DESC NULLS LAST
    """)


@router.get("/monthly")
def monthly():
    return query("""
        SELECT
            TO_CHAR(DATE_TRUNC('month', close_date), 'Mon YY') AS month,
            DATE_TRUNC('month', close_date)                     AS month_date,
            ROUND(SUM(realized_pnl)::numeric, 0)               AS pnl,
            COUNT(*)                                            AS trades
        FROM closed_trades
        WHERE account_id = 1
          AND close_date >= CURRENT_DATE - INTERVAL '18 months'
        GROUP BY DATE_TRUNC('month', close_date)
        ORDER BY month_date
    """)


@router.get("/by-strategy")
def by_strategy():
    return query("""
        SELECT
            strategy,
            ROUND(SUM(realized_pnl) FILTER (WHERE EXTRACT(YEAR FROM close_date) = EXTRACT(YEAR FROM CURRENT_DATE)), 0) AS ytd,
            ROUND(SUM(realized_pnl) FILTER (WHERE close_date >= CURRENT_DATE - INTERVAL '1 year'), 0)                  AS one_year,
            COUNT(*) FILTER (WHERE EXTRACT(YEAR FROM close_date) = EXTRACT(YEAR FROM CURRENT_DATE))                    AS ytd_trades
        FROM closed_trades
        WHERE account_id = 1 AND strategy IS NOT NULL
        GROUP BY strategy
        ORDER BY one_year DESC NULLS LAST
    """)
