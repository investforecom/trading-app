"""
Fundamentals fetch — wraps yfinance and normalizes into a flat dict used by
the Quality Screen, the DCF form, and Claude's thesis context.
"""

import statistics
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf


def fetch_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info or {}

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise ValueError(f"No market data found for ticker {ticker!r}")

    revenue_history = _annual_history(t, "Total Revenue")
    shares_history = _annual_history(t, "Ordinary Shares Number", statement="balance_sheet")
    income_statement_history = _income_statement_history(t)
    cash_flow_history = _cash_flow_history(t)

    # Own-history multiples and peer/sector medians are each a slow network
    # round trip (price history download / several peer .info calls) — run
    # them side by side rather than back to back.
    with ThreadPoolExecutor(max_workers=2) as pool:
        valuation_history_fut = pool.submit(_own_valuation_history, t)
        peer_benchmark_fut = pool.submit(_peer_benchmark, ticker.upper(), info.get("industryKey"))
        valuation_history = valuation_history_fut.result()
        peer_benchmark = peer_benchmark_fut.result()

    total_debt = info.get("totalDebt") or 0
    total_cash = info.get("totalCash") or 0
    net_debt = total_debt - total_cash

    revenue_ttm = info.get("totalRevenue")
    ebitda_margin = info.get("ebitdaMargins")
    ebitda = revenue_ttm * ebitda_margin if revenue_ttm and ebitda_margin else None
    net_debt_to_ebitda = net_debt / ebitda if ebitda else None

    gross_margin = info.get("grossMargins")
    operating_margin = info.get("operatingMargins")
    gross_profit_ttm = revenue_ttm * gross_margin if revenue_ttm and gross_margin else None
    operating_income_ttm = revenue_ttm * operating_margin if revenue_ttm and operating_margin else None

    # Capex has no direct TTM field in yfinance. Deriving it as OCF_ttm -
    # FCF_ttm looked elegant but doesn't reconcile in practice — Yahoo's TTM
    # freeCashflow evidently uses a more conservative convention than plain
    # OCF - Capex (checked against NVDA: the implied "capex" from that
    # subtraction was ~13x the actual capex reported in the cash flow
    # statement). Using the cash flow statement's own most-recent-FY capex
    # instead — less current than true TTM, but numerically real.
    operating_cashflow_ttm = info.get("operatingCashflow")
    free_cashflow_ttm = info.get("freeCashflow")
    capex_ttm = cash_flow_history[-1]["capex"] if cash_flow_history else None

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

        # ── DCF driver inputs ────────────────────────────────────────────
        "net_income_ttm": info.get("netIncomeToCommon"),
        "net_income_yoy": _yoy(_pluck(income_statement_history, "net_income"), "net_income"),
        "net_income_cagr": _cagr(_pluck(income_statement_history, "net_income"), "net_income"),

        # ── Reliability (income statement growth) ─────────────────────────
        "revenue_ttm": revenue_ttm,
        "revenue_growth_yoy": _yoy(revenue_history, "revenue"),
        "revenue_history": revenue_history,
        "revenue_cagr": _cagr(revenue_history, "revenue"),
        "gross_profit_ttm": gross_profit_ttm,
        "gross_profit_yoy": _yoy(_pluck(income_statement_history, "gross_profit"), "gross_profit"),
        "gross_profit_cagr": _cagr(_pluck(income_statement_history, "gross_profit"), "gross_profit"),
        "operating_income_ttm": operating_income_ttm,
        "operating_income_yoy": _yoy(_pluck(income_statement_history, "operating_income"), "operating_income"),
        "operating_income_cagr": _cagr(_pluck(income_statement_history, "operating_income"), "operating_income"),
        "income_statement_history": income_statement_history,
        "analyst_recommendation": info.get("recommendationKey"),
        "number_of_analysts": info.get("numberOfAnalystOpinions"),

        # ── Cash conversion ────────────────────────────────────────────────
        "operating_cashflow_ttm": operating_cashflow_ttm,
        "operating_cashflow_yoy": _yoy(_pluck(cash_flow_history, "operating_cash_flow"), "ocf"),
        "operating_cashflow_cagr": _cagr(_pluck(cash_flow_history, "operating_cash_flow"), "ocf"),
        "capex_ttm": capex_ttm,
        "capex_yoy": _yoy(_pluck(cash_flow_history, "capex"), "capex"),
        "capex_cagr": _cagr(_pluck(cash_flow_history, "capex"), "capex"),
        "fcf_yoy": _yoy(_pluck(cash_flow_history, "fcf"), "fcf"),
        "fcf_cagr": _cagr(_pluck(cash_flow_history, "fcf"), "fcf"),
        "cash_flow_history": cash_flow_history,

        # ── Profitability & efficiency ───────────────────────────────────
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "ebitda_margin": ebitda_margin,
        "profit_margin": info.get("profitMargins"),
        "free_cashflow": free_cashflow_ttm,
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
        "valuation_history": valuation_history,
        "own_pe_median": _median_of(valuation_history, "pe"),
        "own_ps_median": _median_of(valuation_history, "ps"),
        "own_pb_median": _median_of(valuation_history, "pb"),
        "peer_benchmark": peer_benchmark,

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


def _pluck(history: list[dict], field: str) -> list[dict]:
    """Extract one field from a multi-field history list into the {fiscal_year_end, value} shape _cagr/_yoy expect."""
    return [{"fiscal_year_end": r["fiscal_year_end"], "value": r[field]} for r in history]


def _cash_flow_history(t: "yf.Ticker") -> list[dict]:
    """Operating cash flow, capex, and FCF together, oldest first — the
    quality-screen Cash subsection's chart. Capex shown as a positive
    magnitude (the cash flow statement reports it negative). Only years with
    all three present."""
    rows = {
        "operating_cash_flow": "Operating Cash Flow",
        "capex": "Capital Expenditure",
        "fcf": "Free Cash Flow",
    }
    try:
        cf = t.cashflow
        if cf is None or cf.empty or any(name not in cf.index for name in rows.values()):
            return []
        out = []
        for col in sorted(cf.columns):
            values = {key: cf.loc[name, col] for key, name in rows.items()}
            if any(v is None or v != v for v in values.values()):  # NaN check
                continue
            out.append({
                "fiscal_year_end": str(col.date()),
                "operating_cash_flow": float(values["operating_cash_flow"]),
                "capex": abs(float(values["capex"])),
                "fcf": float(values["fcf"]),
            })
        return out
    except Exception:
        return []


def _own_valuation_history(t: "yf.Ticker") -> list[dict]:
    """P/E, P/S, P/B at each of the last few fiscal year-ends, computed from the
    statements plus the historical close nearest each year-end. Benchmarks
    today's multiples against the company's own trading range, not the market's."""
    try:
        fin = t.financials
        bs = t.balance_sheet
        required = ["Diluted EPS", "Total Revenue", "Diluted Average Shares"]
        if fin is None or fin.empty or any(r not in fin.index for r in required):
            return []
        if bs is None or bs.empty or "Stockholders Equity" not in bs.index:
            return []

        hist = t.history(period="6y", auto_adjust=True)
        if hist is None or hist.empty:
            return []
        closes = hist["Close"]
        if closes.index.tz is not None:
            closes.index = closes.index.tz_localize(None)

        out = []
        for col in sorted(fin.columns):
            eps = fin.loc["Diluted EPS", col]
            revenue = fin.loc["Total Revenue", col]
            shares = fin.loc["Diluted Average Shares", col]
            equity = bs.loc["Stockholders Equity", col] if col in bs.columns else None
            if any(v is None or v != v for v in [eps, revenue, shares, equity]):
                continue

            price_series = closes[closes.index <= col]
            if price_series.empty:
                continue
            price = float(price_series.iloc[-1])

            pe = price / eps if eps > 0 else None
            ps = price / (revenue / shares) if shares else None
            pb = price / (equity / shares) if equity > 0 and shares else None

            out.append({
                "fiscal_year_end": str(col.date()),
                "pe": round(pe, 2) if pe else None,
                "ps": round(ps, 2) if ps else None,
                "pb": round(pb, 2) if pb else None,
            })
        return out
    except Exception:
        return []


# Sanity bounds per multiple — screens out bad ADR/currency-mismatch data
# (e.g. a foreign ADR occasionally reports a P/S two orders of magnitude off).
_MULTIPLE_BOUNDS = {
    "pe": (0, 500), "forward_pe": (0, 500), "ps": (0.1, 100), "pb": (0, 100),
    "peg": (0, 20), "ev_ebitda": (0, 100),
}


def _peer_benchmark(ticker: str, industry_key: str | None, max_peers: int = 5) -> dict:
    """Median P/E, forward P/E, P/S, P/B, EV/EBITDA, PEG across same-industry
    peers, via yfinance's Industry.top_companies list. Best-effort — returns
    {} on any failure."""
    if not industry_key:
        return {}
    try:
        top = yf.Industry(industry_key).top_companies
        if top is None or top.empty:
            return {}
        peers = [s for s in top.index.tolist() if s.upper() != ticker][:max_peers]
        if not peers:
            return {}

        def fetch_one(sym: str) -> dict | None:
            try:
                i = yf.Ticker(sym).info
                return {
                    "symbol": sym,
                    "pe": i.get("trailingPE"),
                    "forward_pe": i.get("forwardPE"),
                    "ps": i.get("priceToSalesTrailing12Months"),
                    "pb": i.get("priceToBook"),
                    "ev_ebitda": i.get("enterpriseToEbitda"),
                    "peg": i.get("pegRatio") or i.get("trailingPegRatio"),
                }
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = [r for r in pool.map(fetch_one, peers) if r]

        def median(key: str) -> float | None:
            lo, hi = _MULTIPLE_BOUNDS[key]
            vals = [r[key] for r in results if r.get(key) and lo <= r[key] <= hi]
            return round(statistics.median(vals), 2) if vals else None

        return {
            "peer_count": len(results),
            "peers": sorted(r["symbol"] for r in results),
            "median_pe": median("pe"),
            "median_forward_pe": median("forward_pe"),
            "median_ps": median("ps"),
            "median_pb": median("pb"),
            "median_ev_ebitda": median("ev_ebitda"),
            "median_peg": median("peg"),
        }
    except Exception:
        return {}


def _median_of(history: list[dict], key: str) -> float | None:
    vals = [h[key] for h in history if h.get(key) is not None]
    return round(statistics.median(vals), 2) if vals else None


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
