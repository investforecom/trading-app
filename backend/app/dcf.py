"""
Discounted cash flow calculator — pure functions, no I/O.

Model: FCF-margin DCF. For each scenario, revenue grows for `years` at a rate
that fades linearly from `growth_start` to `growth_end`, FCF is `fcf_margin`
of revenue each year, and a Gordon-growth terminal value is added at the end.
Enterprise value bridges to equity value via net debt, then divides by shares
outstanding for an implied price per share.

This is deliberately simple (no full 3-statement build) — good enough for a
personal thesis tool, fully auditable, and every assumption is explicit.
"""

from dataclasses import dataclass, asdict


@dataclass
class ScenarioInputs:
    growth_start: float      # Y1 revenue growth rate, e.g. 0.15 for 15%
    growth_end: float        # terminal-approach growth rate by year N, e.g. 0.06
    fcf_margin: float        # FCF as % of revenue, e.g. 0.20
    wacc: float              # discount rate, e.g. 0.10
    terminal_growth: float   # perpetuity growth rate, e.g. 0.03


@dataclass
class DCFInputs:
    revenue_ttm: float
    shares_outstanding: float
    net_debt: float           # total debt - cash; can be negative (net cash)
    years: int
    bear: ScenarioInputs
    base: ScenarioInputs
    bull: ScenarioInputs


def _linspace(start: float, end: float, n: int) -> list[float]:
    if n == 1:
        return [end]
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


def _run_scenario(revenue_ttm: float, shares: float, net_debt: float,
                   years: int, s: ScenarioInputs) -> dict:
    if s.wacc <= s.terminal_growth:
        raise ValueError("WACC must exceed terminal growth rate")

    growth_path = _linspace(s.growth_start, s.growth_end, years)

    revenue = revenue_ttm
    rows = []
    pv_sum = 0.0
    for year, g in enumerate(growth_path, start=1):
        revenue = revenue * (1 + g)
        fcf = revenue * s.fcf_margin
        discount = (1 + s.wacc) ** year
        pv = fcf / discount
        pv_sum += pv
        rows.append({
            "year": year,
            "growth": round(g, 4),
            "revenue": round(revenue, 2),
            "fcf": round(fcf, 2),
            "pv_fcf": round(pv, 2),
        })

    terminal_fcf = rows[-1]["fcf"] * (1 + s.terminal_growth)
    terminal_value = terminal_fcf / (s.wacc - s.terminal_growth)
    pv_terminal = terminal_value / ((1 + s.wacc) ** years)

    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - net_debt
    implied_price = equity_value / shares if shares else None

    return {
        "assumptions": asdict(s),
        "projection": rows,
        "terminal_value": round(terminal_value, 2),
        "pv_explicit_fcf": round(pv_sum, 2),
        "pv_terminal_value": round(pv_terminal, 2),
        "enterprise_value": round(enterprise_value, 2),
        "equity_value": round(equity_value, 2),
        "implied_price": round(implied_price, 2) if implied_price is not None else None,
    }


def run_dcf(inputs: DCFInputs) -> dict:
    scenarios = {
        "bear": _run_scenario(inputs.revenue_ttm, inputs.shares_outstanding,
                               inputs.net_debt, inputs.years, inputs.bear),
        "base": _run_scenario(inputs.revenue_ttm, inputs.shares_outstanding,
                               inputs.net_debt, inputs.years, inputs.base),
        "bull": _run_scenario(inputs.revenue_ttm, inputs.shares_outstanding,
                               inputs.net_debt, inputs.years, inputs.bull),
    }
    scenarios["sensitivity"] = _sensitivity_table(
        inputs.revenue_ttm, inputs.shares_outstanding, inputs.net_debt,
        inputs.years, inputs.base,
    )
    return scenarios


def _sensitivity_table(revenue_ttm: float, shares: float, net_debt: float,
                        years: int, base: ScenarioInputs) -> dict:
    """5x5 grid of implied price varying WACC and terminal growth around the base case."""
    wacc_steps = [base.wacc + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    tg_steps = [base.terminal_growth + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]

    grid = []
    for w in wacc_steps:
        row = []
        for tg in tg_steps:
            if w <= tg:
                row.append(None)
                continue
            s = ScenarioInputs(base.growth_start, base.growth_end, base.fcf_margin, w, tg)
            result = _run_scenario(revenue_ttm, shares, net_debt, years, s)
            row.append(result["implied_price"])
        grid.append(row)

    return {
        "wacc_axis": [round(w, 4) for w in wacc_steps],
        "terminal_growth_axis": [round(tg, 4) for tg in tg_steps],
        "grid": grid,
    }
