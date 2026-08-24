import json
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import query, query_one
from app.fundamentals import fetch_fundamentals, search_tickers, recommend_driver
from app.dcf import DCFInputs, ScenarioInputs, run_dcf
from app.thesis_ai import generate_thesis
from app.thesis_qa import generate_thesis_qa

router = APIRouter()

OWNER_ID = 1

# What fundamentals field backs each DCF driver's starting value.
DRIVER_FIELD = {"fcf": "free_cashflow", "revenue": "revenue_ttm", "net_income": "net_income_ttm"}


# ── Request bodies ──────────────────────────────────────────────────────────

class ScenarioBody(BaseModel):
    stage1_growth: float
    stage1_decay: float
    stage1_years: int
    stage2_growth: float = 0
    stage2_years: int = 0
    terminal_growth: float = 0.025
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon"
    exit_multiple: Optional[float] = None
    discount_rate: float = 0.09


class GenerateBody(BaseModel):
    driver: Literal["fcf", "revenue", "net_income"] = "fcf"
    starting_value: Optional[float] = None
    shares_outstanding: Optional[float] = None
    net_debt: Optional[float] = None
    include_net_debt_bridge: bool = True
    dilution_rate: float = 0
    dilution_years: int = 0
    bear: ScenarioBody
    base: ScenarioBody
    bull: ScenarioBody


# ── Fundamentals history ─────────────────────────────────────────────────────
# Append-only, like investment_theses — every fetch is a new row. "Current"
# is just the latest one, so nothing is re-pulled from yfinance unless the
# user explicitly hits Refresh Data, but every past pull stays revisitable.

def _latest_fundamentals(ticker: str) -> dict | None:
    row = query_one("""
        SELECT id, data_json, fetched_at FROM ticker_fundamentals_snapshots
        WHERE owner_id = %s AND ticker = %s
        ORDER BY fetched_at DESC LIMIT 1
    """, (OWNER_ID, ticker))
    if not row:
        return None
    return {**row["data_json"], "_snapshot_id": row["id"], "_cached_at": row["fetched_at"].isoformat()}


def _insert_fundamentals_snapshot(ticker: str, data: dict) -> dict:
    row = query_one("""
        INSERT INTO ticker_fundamentals_snapshots (owner_id, ticker, current_price, data_json)
        VALUES (%s, %s, %s, %s)
        RETURNING id, fetched_at
    """, (OWNER_ID, ticker, data.get("current_price"), _json(data)))
    return {**data, "_snapshot_id": row["id"], "_cached_at": row["fetched_at"].isoformat()}


def _get_or_fetch_fundamentals(ticker: str) -> dict:
    """Cache-first fundamentals lookup — fetches from yfinance only when no snapshot exists yet."""
    latest = _latest_fundamentals(ticker)
    if latest:
        return latest
    return _insert_fundamentals_snapshot(ticker, fetch_fundamentals(ticker))


# ── Thesis (business Q&A) history ────────────────────────────────────────────

def _latest_thesis_qa(ticker: str) -> dict | None:
    row = query_one("""
        SELECT id, data_json, generated_at, based_on_fetched_at FROM ticker_thesis_snapshots
        WHERE owner_id = %s AND ticker = %s
        ORDER BY generated_at DESC LIMIT 1
    """, (OWNER_ID, ticker))
    if not row:
        return None
    return {
        **row["data_json"],
        "_snapshot_id": row["id"],
        "_generated_at": row["generated_at"].isoformat(),
        "_based_on_fetched_at": row["based_on_fetched_at"].isoformat() if row["based_on_fetched_at"] else None,
    }


def _insert_thesis_snapshot(ticker: str, data: dict, based_on_fetched_at: str | None) -> dict:
    row = query_one("""
        INSERT INTO ticker_thesis_snapshots (owner_id, ticker, based_on_fetched_at, data_json)
        VALUES (%s, %s, %s, %s)
        RETURNING id, generated_at
    """, (OWNER_ID, ticker, based_on_fetched_at, _json(data)))
    return {
        **data,
        "_snapshot_id": row["id"],
        "_generated_at": row["generated_at"].isoformat(),
        "_based_on_fetched_at": based_on_fetched_at,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/search")
def search(q: str):
    """Ticker/company-name lookup — the pre-search gate before starting a thesis."""
    try:
        return search_tickers(q)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.get("/tickers")
def list_tickers():
    """Tickers with at least one saved thesis, most recently updated first."""
    return query("""
        SELECT DISTINCT ON (ticker)
            ticker, id AS latest_run_id, created_at, target_price,
            fair_value_bear, fair_value_base, fair_value_bull, current_price
        FROM investment_theses
        WHERE owner_id = %s
        ORDER BY ticker, created_at DESC
    """, (OWNER_ID,))


@router.get("/{ticker}/history")
def history(ticker: str):
    return query("""
        SELECT id, created_at, current_price, target_price,
               fair_value_bear, fair_value_base, fair_value_bull
        FROM investment_theses
        WHERE owner_id = %s AND ticker = %s
        ORDER BY created_at DESC
    """, (OWNER_ID, ticker.upper()))


@router.get("/run/{run_id}")
def get_run(run_id: int):
    row = query_one("""
        SELECT * FROM investment_theses WHERE id = %s AND owner_id = %s
    """, (run_id, OWNER_ID))
    if not row:
        raise HTTPException(404, "Thesis run not found")
    return row


@router.get("/{ticker}/fundamentals")
def get_fundamentals(ticker: str):
    """Cache-first fundamentals — the normal way the Quality Screen loads data."""
    ticker = ticker.upper()
    try:
        return _get_or_fetch_fundamentals(ticker)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/{ticker}/fetch")
def fetch(ticker: str):
    """Force a live re-pull from yfinance — the Refresh Data button. Always adds a new snapshot."""
    ticker = ticker.upper()
    try:
        data = fetch_fundamentals(ticker)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return _insert_fundamentals_snapshot(ticker, data)


@router.get("/{ticker}/fundamentals/history")
def fundamentals_history(ticker: str):
    return query("""
        SELECT id, fetched_at, current_price FROM ticker_fundamentals_snapshots
        WHERE owner_id = %s AND ticker = %s
        ORDER BY fetched_at DESC
    """, (OWNER_ID, ticker.upper()))


@router.get("/{ticker}/fundamentals/snapshot/{snapshot_id}")
def fundamentals_snapshot(ticker: str, snapshot_id: int):
    row = query_one("""
        SELECT data_json, fetched_at FROM ticker_fundamentals_snapshots
        WHERE id = %s AND owner_id = %s AND ticker = %s
    """, (snapshot_id, OWNER_ID, ticker.upper()))
    if not row:
        raise HTTPException(404, "Fundamentals snapshot not found")
    return {**row["data_json"], "_snapshot_id": snapshot_id, "_cached_at": row["fetched_at"].isoformat()}


@router.get("/{ticker}/thesis-qa")
def get_thesis_qa(ticker: str):
    """Cache-first Thesis stage read. 404 if nothing has been generated yet."""
    latest = _latest_thesis_qa(ticker.upper())
    if not latest:
        raise HTTPException(404, "No thesis generated yet")
    return latest


@router.get("/{ticker}/thesis-qa/history")
def thesis_qa_history(ticker: str):
    return query("""
        SELECT id, generated_at, data_json->>'stage' AS stage, data_json->>'thesis_text' AS thesis_text
        FROM ticker_thesis_snapshots
        WHERE owner_id = %s AND ticker = %s
        ORDER BY generated_at DESC
    """, (OWNER_ID, ticker.upper()))


@router.get("/{ticker}/thesis-qa/snapshot/{snapshot_id}")
def thesis_qa_snapshot(ticker: str, snapshot_id: int):
    row = query_one("""
        SELECT data_json, generated_at, based_on_fetched_at FROM ticker_thesis_snapshots
        WHERE id = %s AND owner_id = %s AND ticker = %s
    """, (snapshot_id, OWNER_ID, ticker.upper()))
    if not row:
        raise HTTPException(404, "Thesis snapshot not found")
    return {
        **row["data_json"],
        "_snapshot_id": snapshot_id,
        "_generated_at": row["generated_at"].isoformat(),
        "_based_on_fetched_at": row["based_on_fetched_at"].isoformat() if row["based_on_fetched_at"] else None,
    }


@router.post("/{ticker}/thesis-qa/generate")
def generate_thesis_qa_endpoint(ticker: str):
    """
    Answer the business questions and produce the 2-line growth thesis,
    grounded in the cached (or freshly fetched) fundamentals. Always adds a
    new snapshot — past theses stay revisitable, same as DCF runs.
    """
    ticker = ticker.upper()
    try:
        fundamentals = _get_or_fetch_fundamentals(ticker)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    recommended = recommend_driver(fundamentals)

    try:
        qa = generate_thesis_qa(ticker, fundamentals, recommended)
    except Exception as exc:
        raise HTTPException(502, f"Thesis generation failed: {exc}")

    return _insert_thesis_snapshot(ticker, qa, fundamentals.get("_cached_at"))


@router.post("/{ticker}/generate")
def generate(ticker: str, body: GenerateBody):
    """
    Run the 3-scenario DCF against cached fundamentals, call Claude for the
    written thesis + risks, and save the whole run as a new row (history is
    never overwritten).
    """
    ticker = ticker.upper()
    try:
        fundamentals = _get_or_fetch_fundamentals(ticker)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    driver_field = DRIVER_FIELD[body.driver]
    starting_value = body.starting_value or fundamentals.get(driver_field)
    shares = body.shares_outstanding or fundamentals.get("shares_outstanding")
    net_debt = body.net_debt if body.net_debt is not None else fundamentals.get("net_debt", 0)

    if not starting_value or not shares:
        raise HTTPException(400, f"Missing {driver_field} or shares_outstanding — yfinance data incomplete, supply manually")

    dcf_inputs = DCFInputs(
        driver=body.driver,
        starting_value=starting_value,
        shares_outstanding=shares,
        net_debt=net_debt,
        include_net_debt_bridge=body.include_net_debt_bridge,
        dilution_rate=body.dilution_rate,
        dilution_years=body.dilution_years,
        bear=ScenarioInputs(**body.bear.model_dump()),
        base=ScenarioInputs(**body.base.model_dump()),
        bull=ScenarioInputs(**body.bull.model_dump()),
    )
    try:
        dcf_outputs = run_dcf(dcf_inputs)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    try:
        ai_result = generate_thesis(ticker, fundamentals, dcf_outputs)
    except Exception as exc:
        raise HTTPException(502, f"Thesis generation failed: {exc}")

    missing = [k for k in ("thesis_text", "top_risks", "scenario_commentary", "target_price") if k not in ai_result]
    if missing:
        raise HTTPException(502, f"Thesis generation returned an incomplete response — missing {', '.join(missing)}")

    row = query_one("""
        INSERT INTO investment_theses (
            owner_id, ticker, current_price,
            fundamentals_json, dcf_inputs_json, dcf_outputs_json,
            fair_value_bear, fair_value_base, fair_value_bull, target_price,
            thesis_text, risks_json
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING *
    """, (
        OWNER_ID, ticker, fundamentals.get("current_price"),
        _json(fundamentals), _json(body.model_dump()), _json({**dcf_outputs, "scenario_commentary": ai_result["scenario_commentary"]}),
        dcf_outputs["bear"]["implied_price"], dcf_outputs["base"]["implied_price"], dcf_outputs["bull"]["implied_price"],
        ai_result["target_price"], ai_result["thesis_text"], _json(ai_result["top_risks"]),
    ))
    return row


def _json(obj):
    return json.dumps(obj, default=str)
