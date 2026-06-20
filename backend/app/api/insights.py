from fastapi import APIRouter
from app.db import query, query_one

router = APIRouter()


@router.get("/latest")
def latest():
    run = query_one("""
        SELECT id, run_date, narrative
        FROM analysis_runs
        WHERE account_id = 1
        ORDER BY run_date DESC LIMIT 1
    """)
    if not run:
        return {"run": None, "insights": []}
    items = query("""
        SELECT category, severity, title, body
        FROM insights
        WHERE run_id = %s
        ORDER BY CASE severity WHEN 'ACTION' THEN 1 WHEN 'WATCH' THEN 2 ELSE 3 END, category
    """, (run["id"],))
    return {"run": run, "insights": items}


@router.get("/history")
def history():
    return query("""
        SELECT
            ar.run_date,
            COUNT(*) FILTER (WHERE i.severity = 'ACTION') AS actions,
            COUNT(*) FILTER (WHERE i.severity = 'WATCH')  AS watches,
            COUNT(*) FILTER (WHERE i.severity = 'INFO')   AS infos
        FROM analysis_runs ar
        LEFT JOIN insights i ON i.run_id = ar.id
        WHERE ar.account_id = 1
        GROUP BY ar.run_date
        ORDER BY ar.run_date DESC
        LIMIT 20
    """)
