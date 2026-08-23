"""
Fundamentals fetch — wraps yfinance and normalizes into a flat dict used to
prefill the DCF form and give Claude context for the written thesis.
"""

import yfinance as yf


def fetch_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info or {}

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise ValueError(f"No market data found for ticker {ticker!r}")

    revenue_history = _revenue_history(t)

    total_debt = info.get("totalDebt") or 0
    total_cash = info.get("totalCash") or 0

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

        "revenue_ttm": info.get("totalRevenue"),
        "revenue_growth_yoy": info.get("revenueGrowth"),
        "revenue_history": revenue_history,

        "gross_margin": info.get("grossMargins"),
        "operating_margin": info.get("operatingMargins"),
        "ebitda_margin": info.get("ebitdaMargins"),
        "profit_margin": info.get("profitMargins"),
        "free_cashflow": info.get("freeCashflow"),

        "total_debt": total_debt,
        "total_cash": total_cash,
        "net_debt": total_debt - total_cash,

        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "peg_ratio": info.get("pegRatio") or info.get("trailingPegRatio"),

        "analyst_target_mean": info.get("targetMeanPrice"),
        "analyst_target_low": info.get("targetLowPrice"),
        "analyst_target_high": info.get("targetHighPrice"),
        "analyst_recommendation": info.get("recommendationKey"),
        "number_of_analysts": info.get("numberOfAnalystOpinions"),
    }


def _revenue_history(t: "yf.Ticker") -> list[dict]:
    """Last few fiscal years of annual revenue, oldest first, for CAGR context."""
    try:
        financials = t.financials
        if financials is None or financials.empty or "Total Revenue" not in financials.index:
            return []
        row = financials.loc["Total Revenue"].dropna().sort_index()
        return [
            {"fiscal_year_end": str(col.date()), "revenue": float(val)}
            for col, val in row.items()
        ]
    except Exception:
        return []
