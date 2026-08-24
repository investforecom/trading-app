"""
Discounted cash flow calculator — pure functions, no I/O.

Driver-agnostic 3-stage DCF: Stage 1 grows at `stage1_growth`, decaying by
`stage1_decay` per year, for `stage1_years`; an optional flat Stage 2 follows
for `stage2_years` (0 = skip — a plain 2-stage model); then a terminal value
via Gordon growth and/or an exit multiple (both are always computed so each
can be sanity-checked against the other, regardless of which one feeds the
headline implied price).

Works on any of three driver metrics:
  - fcf:        classic FCFF-style DCF; net-debt bridge optional (default on)
  - revenue:    for pre-FCF growth companies; terminal is exit-multiple only —
                perpetuity-growing raw revenue as if it were cash isn't
                economically coherent, so Gordon growth is not offered
  - net_income: for banks/insurers where FCF/capex isn't meaningful; already
                equity-level (post-interest), so the net-debt bridge is
                forced off regardless of the include_net_debt_bridge flag

Forward dilution: shares grow at `dilution_rate` for `dilution_years` then
flatten. Equity value is divided by the *diluted* (post-dilution) share
count — today's shareholders' claim on the terminal value is shrunk by the
same dilution the projection assumes, which is the standard simplified
treatment (vs. modeling year-by-year ownership).
"""

from dataclasses import dataclass, asdict
from typing import Literal, Optional

Driver = Literal["fcf", "revenue", "net_income"]
TerminalMethod = Literal["gordon", "exit_multiple"]


@dataclass
class ScenarioInputs:
    stage1_growth: float
    stage1_decay: float           # pp/year decline in growth during stage 1, e.g. 0.03 for 3pp/yr
    stage1_years: int
    stage2_growth: float = 0.0    # flat growth for stage 2; ignored if stage2_years == 0
    stage2_years: int = 0         # 0 = skip stage 2 (pure 2-stage: decay then terminal)
    terminal_growth: float = 0.025
    terminal_method: TerminalMethod = "gordon"
    exit_multiple: Optional[float] = None   # x of terminal-year driver value
    discount_rate: float = 0.09


@dataclass
class DCFInputs:
    driver: Driver
    starting_value: float           # TTM FCF / Revenue / Net Income, $
    shares_outstanding: float
    net_debt: float
    include_net_debt_bridge: bool   # forced off when driver == "net_income"
    dilution_rate: float            # annual, e.g. 0.02 for 2%/yr
    dilution_years: int
    bear: ScenarioInputs
    base: ScenarioInputs
    bull: ScenarioInputs


def _growth_path(s: ScenarioInputs) -> list[float]:
    path = []
    g = s.stage1_growth
    for _ in range(s.stage1_years):
        path.append(g)
        g -= s.stage1_decay
    if s.stage2_years > 0:
        path.extend([s.stage2_growth] * s.stage2_years)
    return path


def _implied_multiple_from_gordon(terminal_growth: float, discount_rate: float) -> Optional[float]:
    if discount_rate <= terminal_growth:
        return None
    return (1 + terminal_growth) / (discount_rate - terminal_growth)


def _implied_growth_from_multiple(exit_multiple: float, discount_rate: float) -> Optional[float]:
    denom = 1 + exit_multiple
    if denom == 0:
        return None
    return (exit_multiple * discount_rate - 1) / denom


def _run_scenario(driver: Driver, starting_value: float, shares: float, net_debt: float,
                   include_bridge: bool, dilution_rate: float, dilution_years: int,
                   s: ScenarioInputs) -> dict:
    growth_path = _growth_path(s)
    years = len(growth_path)
    if years == 0:
        raise ValueError("Stage 1 + Stage 2 years must total at least 1")
    if s.terminal_method == "gordon" and s.discount_rate <= s.terminal_growth:
        raise ValueError("Discount rate must exceed terminal growth rate for the Gordon growth method")
    if s.terminal_method == "exit_multiple" and not s.exit_multiple:
        raise ValueError("Exit multiple method requires exit_multiple to be set")

    value = starting_value
    rows = []
    pv_sum = 0.0
    for year, g in enumerate(growth_path, start=1):
        value = value * (1 + g)
        discount = (1 + s.discount_rate) ** year
        pv = value / discount
        pv_sum += pv
        rows.append({"year": year, "growth": round(g, 4), "value": round(value, 2), "pv": round(pv, 2)})

    terminal_value = rows[-1]["value"]  # last explicit-year value, before terminal growth/multiple applied

    terminal_value_gordon = None
    if s.discount_rate > s.terminal_growth:
        terminal_fcf = terminal_value * (1 + s.terminal_growth)
        terminal_value_gordon = terminal_fcf / (s.discount_rate - s.terminal_growth)

    terminal_value_exit = terminal_value * s.exit_multiple if s.exit_multiple else None

    chosen_terminal = terminal_value_gordon if s.terminal_method == "gordon" else terminal_value_exit
    pv_terminal = chosen_terminal / ((1 + s.discount_rate) ** years)

    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - net_debt if include_bridge else enterprise_value

    diluted_shares = shares * ((1 + dilution_rate) ** dilution_years) if shares else None
    implied_price = equity_value / diluted_shares if diluted_shares else None

    return {
        "assumptions": asdict(s),
        "projection": rows,
        "terminal_value_gordon": round(terminal_value_gordon, 2) if terminal_value_gordon is not None else None,
        "terminal_value_exit_multiple": round(terminal_value_exit, 2) if terminal_value_exit is not None else None,
        "implied_exit_multiple_from_gordon": round(_implied_multiple_from_gordon(s.terminal_growth, s.discount_rate) or 0, 2) if terminal_value_gordon is not None else None,
        "implied_perpetuity_growth_from_exit_multiple": round(_implied_growth_from_multiple(s.exit_multiple, s.discount_rate), 4) if s.exit_multiple else None,
        "terminal_method_used": s.terminal_method,
        "pv_explicit": round(pv_sum, 2),
        "pv_terminal": round(pv_terminal, 2),
        "enterprise_value": round(enterprise_value, 2),
        "net_debt_bridge_applied": include_bridge,
        "equity_value": round(equity_value, 2),
        "diluted_shares": round(diluted_shares, 2) if diluted_shares else None,
        "implied_price": round(implied_price, 2) if implied_price is not None else None,
    }


def run_dcf(inputs: DCFInputs) -> dict:
    include_bridge = inputs.include_net_debt_bridge and inputs.driver != "net_income"

    def run(s: ScenarioInputs) -> dict:
        return _run_scenario(inputs.driver, inputs.starting_value, inputs.shares_outstanding,
                              inputs.net_debt, include_bridge, inputs.dilution_rate,
                              inputs.dilution_years, s)

    scenarios = {
        "driver": inputs.driver,
        "net_debt_bridge_applied": include_bridge,
        "bear": run(inputs.bear),
        "base": run(inputs.base),
        "bull": run(inputs.bull),
    }
    scenarios["sensitivity"] = _sensitivity_table(inputs, include_bridge)
    return scenarios


def _sensitivity_table(inputs: DCFInputs, include_bridge: bool) -> dict:
    """5x5 grid of implied price varying discount rate and terminal growth
    around the base case. Always uses the Gordon growth method for the grid,
    regardless of which terminal method the base case actually uses."""
    base = inputs.base
    discount_steps = [base.discount_rate + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    tg_steps = [base.terminal_growth + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]

    grid = []
    for r in discount_steps:
        row = []
        for tg in tg_steps:
            if r <= tg:
                row.append(None)
                continue
            s = ScenarioInputs(
                stage1_growth=base.stage1_growth, stage1_decay=base.stage1_decay, stage1_years=base.stage1_years,
                stage2_growth=base.stage2_growth, stage2_years=base.stage2_years,
                terminal_growth=tg, terminal_method="gordon", discount_rate=r,
            )
            result = _run_scenario(inputs.driver, inputs.starting_value, inputs.shares_outstanding,
                                    inputs.net_debt, include_bridge, inputs.dilution_rate,
                                    inputs.dilution_years, s)
            row.append(result["implied_price"])
        grid.append(row)

    return {
        "discount_rate_axis": [round(r, 4) for r in discount_steps],
        "terminal_growth_axis": [round(tg, 4) for tg in tg_steps],
        "grid": grid,
    }
