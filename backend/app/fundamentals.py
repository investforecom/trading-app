"""
Fundamentals fetch — wraps yfinance and normalizes into a flat dict used by
the Quality Screen, the DCF form, and Claude's thesis context.
"""

import yfinance as yf


def fetch_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info or {}

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise ValueError(f"No market data found for ticker {ticker!r}")

    revenue_history = _annual_history(t, "Total Revenue")
    shares_history = _annual_history(t, "Ordinary Shares Number", statement="balance_sheet")
    income_statement_history = _income_statement_history(t)

    total_debt = info.get("totalDebt") or 0
    total_cash = info.get("totalCash") or 0
    net_debt = total_debt - total_cash

    revenue_ttm = info.get("totalRevenue")
    ebitda_margin = info.get("ebitdaMargins")
    ebitda = revenue_ttm * ebitda_margin if revenue_ttm and ebitda_margin else None
    net_debt_to_ebitda = net_debt / ebitda if ebitda else None

    return {
        "ticker": ticker.upper(),
        "long_name": info.get("longName") or info.get("shortName") or ticker.upper(),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "summary": info.get("longBusinessSummary"),

        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "beta": info.get("beta"),

        # ── Reliability ──────────────────────────────────────────────────
        "revenue_ttm": revenue_ttm,
        "revenue_growth_yoy": info.get("revenueGrowth"),
        "revenue_history": revenue_history,
        "revenue_cagr": _cagr(revenue_history, "revenue"),
        "income_statement_history": income_statement_history,
        "analyst_recommendation": info.get("recommendationKey"),
        "number_of_analysts": info.get("numberOfAnalystOpinions"),

        # ── Profitability & efficiency ───────────────────────────────────
        "gross_margin": info.get("grossMargins"),
        "operating_margin": info.get("operatingMargins"),
        "ebitda_margin": ebitda_margin,
        "profit_margin": info.get("profitMargins"),
        "free_cashflow": info.get("freeCashflow"),
        "return_on_equity": info.get("returnOnEquity"),
        "return_on_assets": info.get("returnOnAssets"),

        # ── Debt & liquidity ─────────────────────────────────────────────
        "debt_to_equity_pct": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "quick_ratio": info.get("quickRatio"),
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "interest_coverage": _interest_coverage(t),

        # ── Dilution ─────────────────────────────────────────────────────
        "shares_history": shares_history,
        "shares_yoy": _yoy(shares_history, "shares"),
        "shares_cagr": _cagr(shares_history, "shares"),
        "insider_pct": info.get("heldPercentInsiders"),
        "institution_pct": info.get("heldPercentInstitutions"),

        # ── Valuation ────────────────────────────────────────────────────
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio") or info.get("trailingPegRatio"),
        "ev_to_ebitda": info.get("enterpriseToEbitda"),
        "price_to_sales": info.get("priceToSalesTrailing12Months"),
        "price_to_book": info.get("priceToBook"),
        "analyst_target_mean": info.get("targetMeanPrice"),
        "analyst_target_low": info.get("targetLowPrice"),
        "analyst_target_high": info.get("targetHighPrice"),

        # ── DCF bridge inputs ────────────────────────────────────────────
        "total_debt": total_debt,
        "total_cash": total_cash,
        "net_debt": net_debt,
    }


def search_tickers(query: str, max_results: int = 8) -> list[dict]:
    """Ticker/company-name lookup for the pre-search gate — disambiguates before
    committing to a symbol (e.g. 'apple' matching AAPL vs. Apple Hospitality REIT,
    or the same company cross-listed on multiple exchanges)."""
    if not query or len(query.strip()) < 2:
        return []
    results = yf.Search(query.strip(), max_results=max_results, news_count=0, lists_count=0).quotes
    return [
        {
            "symbol": r.get("symbol"),
            "name": r.get("longname") or r.get("shortname"),
            "exchange": r.get("exchDisp"),
            "type": r.get("typeDisp"),
            "sector": r.get("sectorDisp"),
        }
        for r in results
        if r.get("symbol") and r.get("quoteType") in ("EQUITY", "ETF")
    ]


def _annual_history(t: "yf.Ticker", row_name: str, statement: str = "financials") -> list[dict]:
    """Last few fiscal years of an annual statement line, oldest first."""
    try:
        df = t.financials if statement == "financials" else t.balance_sheet
        if df is None or df.empty or row_name not in df.index:
            return []
        row = df.loc[row_name].dropna().sort_index()
        return [
            {"fiscal_year_end": str(col.date()), "value": float(val)}
            for col, val in row.items()
        ]
    except Exception:
        return []


def _income_statement_history(t: "yf.Ticker") -> list[dict]:
    """Revenue, gross profit, operating income, and net income together, oldest
    first — the 4-series quality-screen chart. Only years with all four present."""
    rows = {
        "revenue": "Total Revenue",
        "gross_profit": "Gross Profit",
        "operating_income": "Operating Income",
        "net_income": "Net Income",
    }
    try:
        fin = t.financials
        if fin is None or fin.empty or any(name not in fin.index for name in rows.values()):
            return []
        out = []
        for col in sorted(fin.columns):
            values = {key: fin.loc[name, col] for key, name in rows.items()}
            if any(v is None or v != v for v in values.values()):  # NaN check
                continue
            out.append({"fiscal_year_end": str(col.date()), **{k: float(v) for k, v in values.items()}})
        return out
    except Exception:
        return []


def _interest_coverage(t: "yf.Ticker") -> float | None:
    """Most recent EBIT / interest expense — how many times over the company
    covers its interest payments. None when there's effectively no interest expense."""
    try:
        fin = t.financials
        if fin is None or fin.empty or "EBIT" not in fin.index or "Interest Expense" not in fin.index:
            return None
        ebit = fin.loc["EBIT"].dropna()
        interest = fin.loc["Interest Expense"].dropna()
        common = sorted(c for c in ebit.index if c in interest.index)
        if not common:
            return None
        latest = common[-1]
        if not interest[latest]:
            return None
        return float(ebit[latest] / interest[latest])
    except Exception:
        return None


def _yoy(history: list[dict], _label: str) -> float | None:
    """Most recent year-over-year change from an _annual_history series."""
    if len(history) < 2:
        return None
    prev, latest = history[-2]["value"], history[-1]["value"]
    if not prev:
        return None
    return (latest / prev) - 1


def _cagr(history: list[dict], _label: str) -> float | None:
    """Compound annual growth rate across the full _annual_history series."""
    if len(history) < 2:
        return None
    first, last = history[0]["value"], history[-1]["value"]
    years = len(history) - 1
    if not first or first < 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1
