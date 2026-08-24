from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import query, query_one, execute
from app.fundamentals import fetch_fundamentals, search_tickers
from app.dcf import DCFInputs, ScenarioInputs, run_dcf
from app.thesis_ai import generate_thesis

router = APIRouter()

OWNER_ID = 1


# ── Request bodies ──────────────────────────────────────────────────────────

class ScenarioBody(BaseModel):
    growth_start: float
    growth_end: float
    fcf_margin: float
    wacc: float
    terminal_growth: float


class GenerateBody(BaseModel):
    years: int = 5
    shares_outstanding: Optional[float] = None
    net_debt: Optional[float] = None
    revenue_ttm: Optional[float] = None
    bear: ScenarioBody
    base: ScenarioBody
    bull: ScenarioBody


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


@router.post("/{ticker}/fetch")
def fetch(ticker: str):
    """Pull fresh fundamentals from yfinance to prefill the DCF form. Not saved."""
    try:
        return fetch_fundamentals(ticker.upper())
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/{ticker}/generate")
def generate(ticker: str, body: GenerateBody):
    """
    Fetch fundamentals (fresh), run the 3-scenario DCF, call Claude for the
    written thesis + risks, and save the whole run as a new row (history is
    never overwritten).
    """
    ticker = ticker.upper()
    try:
        fundamentals = fetch_fundamentals(ticker)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    revenue_ttm = body.revenue_ttm or fundamentals.get("revenue_ttm")
    shares = body.shares_outstanding or fundamentals.get("shares_outstanding")
    net_debt = body.net_debt if body.net_debt is not None else fundamentals.get("net_debt", 0)

    if not revenue_ttm or not shares:
        raise HTTPException(400, "Missing revenue_ttm or shares_outstanding — yfinance data incomplete, supply manually")

    dcf_inputs = DCFInputs(
        revenue_ttm=revenue_ttm,
        shares_outstanding=shares,
        net_debt=net_debt,
        years=body.years,
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
    import json
    return json.dumps(obj, default=str)
