// Client-side port of backend/app/dcf.py — same math, same field names, so
// live (in-browser) results and saved/historical (server-computed) results
// render through identical components. Runs synchronously on every input
// change: no network round trip, no debounce needed.

export type Driver = 'fcf' | 'revenue' | 'net_income'
export type TerminalMethod = 'gordon' | 'exit_multiple'

export interface ScenarioInputs {
  stage1_growth: number
  stage1_decay: number
  stage1_years: number
  stage2_growth: number
  stage2_years: number
  terminal_growth: number
  terminal_method: TerminalMethod
  exit_multiple: number | null
  discount_rate: number
}

export interface ProjectionRow {
  year: number
  growth: number
  value: number
  pv: number
}

export interface ScenarioResult {
  assumptions: ScenarioInputs
  projection: ProjectionRow[]
  terminal_value_gordon: number | null
  terminal_value_exit_multiple: number | null
  implied_exit_multiple_from_gordon: number | null
  implied_perpetuity_growth_from_exit_multiple: number | null
  terminal_method_used: TerminalMethod
  pv_explicit: number
  pv_terminal: number
  enterprise_value: number
  net_debt_bridge_applied: boolean
  equity_value: number
  diluted_shares: number | null
  implied_price: number | null
  error: string | null
}

export interface SensitivityResult {
  discount_rate_axis: number[]
  terminal_growth_axis: number[]
  grid: (number | null)[][]
}

export interface DcfResult {
  driver: Driver
  net_debt_bridge_applied: boolean
  bear: ScenarioResult
  base: ScenarioResult
  bull: ScenarioResult
  sensitivity: SensitivityResult
}

function growthPath(s: ScenarioInputs): number[] {
  const path: number[] = []
  let g = s.stage1_growth
  for (let i = 0; i < s.stage1_years; i++) {
    path.push(g)
    g -= s.stage1_decay
  }
  if (s.stage2_years > 0) {
    for (let i = 0; i < s.stage2_years; i++) path.push(s.stage2_growth)
  }
  return path
}

export function impliedMultipleFromGordon(terminalGrowth: number, discountRate: number): number | null {
  if (discountRate <= terminalGrowth) return null
  return (1 + terminalGrowth) / (discountRate - terminalGrowth)
}

export function impliedGrowthFromMultiple(exitMultiple: number, discountRate: number): number | null {
  const denom = 1 + exitMultiple
  if (denom === 0) return null
  return (exitMultiple * discountRate - 1) / denom
}

const ERROR_RESULT = (message: string): ScenarioResult => ({
  assumptions: {} as ScenarioInputs, projection: [], terminal_value_gordon: null,
  terminal_value_exit_multiple: null, implied_exit_multiple_from_gordon: null,
  implied_perpetuity_growth_from_exit_multiple: null, terminal_method_used: 'gordon',
  pv_explicit: 0, pv_terminal: 0, enterprise_value: 0, net_debt_bridge_applied: false,
  equity_value: 0, diluted_shares: null, implied_price: null, error: message,
})

export function runScenario(
  startingValue: number, shares: number, netDebt: number, includeBridge: boolean,
  dilutionRate: number, dilutionYears: number, s: ScenarioInputs,
): ScenarioResult {
  const path = growthPath(s)
  const years = path.length
  if (years === 0) return ERROR_RESULT('Stage 1 + Stage 2 years must total at least 1')
  if (s.terminal_method === 'gordon' && s.discount_rate <= s.terminal_growth) {
    return ERROR_RESULT('Discount rate must exceed terminal growth rate for the Gordon growth method')
  }
  if (s.terminal_method === 'exit_multiple' && !s.exit_multiple) {
    return ERROR_RESULT('Exit multiple method requires exit_multiple to be set')
  }

  let value = startingValue
  const rows: ProjectionRow[] = []
  let pvSum = 0
  for (let i = 0; i < path.length; i++) {
    const g = path[i]
    const year = i + 1
    value = value * (1 + g)
    const discount = Math.pow(1 + s.discount_rate, year)
    const pv = value / discount
    pvSum += pv
    rows.push({ year, growth: g, value, pv })
  }

  const terminalBase = rows[rows.length - 1].value
  const terminalValueGordon = s.discount_rate > s.terminal_growth
    ? (terminalBase * (1 + s.terminal_growth)) / (s.discount_rate - s.terminal_growth)
    : null
  const terminalValueExit = s.exit_multiple ? terminalBase * s.exit_multiple : null

  const chosenTerminal = s.terminal_method === 'gordon' ? terminalValueGordon : terminalValueExit
  if (chosenTerminal == null) return ERROR_RESULT('Could not compute a terminal value with the given inputs')

  const pvTerminal = chosenTerminal / Math.pow(1 + s.discount_rate, years)
  const enterpriseValue = pvSum + pvTerminal
  const equityValue = includeBridge ? enterpriseValue - netDebt : enterpriseValue
  const dilutedShares = shares ? shares * Math.pow(1 + dilutionRate, dilutionYears) : null
  const impliedPrice = dilutedShares ? equityValue / dilutedShares : null

  return {
    assumptions: s,
    projection: rows,
    terminal_value_gordon: terminalValueGordon,
    terminal_value_exit_multiple: terminalValueExit,
    implied_exit_multiple_from_gordon: terminalValueGordon != null ? impliedMultipleFromGordon(s.terminal_growth, s.discount_rate) : null,
    implied_perpetuity_growth_from_exit_multiple: s.exit_multiple ? impliedGrowthFromMultiple(s.exit_multiple, s.discount_rate) : null,
    terminal_method_used: s.terminal_method,
    pv_explicit: pvSum,
    pv_terminal: pvTerminal,
    enterprise_value: enterpriseValue,
    net_debt_bridge_applied: includeBridge,
    equity_value: equityValue,
    diluted_shares: dilutedShares,
    implied_price: impliedPrice,
    error: null,
  }
}

function sensitivityTable(
  startingValue: number, shares: number, netDebt: number, includeBridge: boolean,
  dilutionRate: number, dilutionYears: number, base: ScenarioInputs,
): SensitivityResult {
  const discountSteps = [-0.02, -0.01, 0, 0.01, 0.02].map((d) => base.discount_rate + d)
  const tgSteps = [-0.01, -0.005, 0, 0.005, 0.01].map((d) => base.terminal_growth + d)

  const grid: (number | null)[][] = discountSteps.map((r) =>
    tgSteps.map((tg) => {
      if (r <= tg) return null
      const s: ScenarioInputs = {
        stage1_growth: base.stage1_growth, stage1_decay: base.stage1_decay, stage1_years: base.stage1_years,
        stage2_growth: base.stage2_growth, stage2_years: base.stage2_years,
        terminal_growth: tg, terminal_method: 'gordon', exit_multiple: null, discount_rate: r,
      }
      const result = runScenario(startingValue, shares, netDebt, includeBridge, dilutionRate, dilutionYears, s)
      return result.error ? null : result.implied_price
    })
  )

  return { discount_rate_axis: discountSteps, terminal_growth_axis: tgSteps, grid }
}

export function runDcf(
  driver: Driver, startingValue: number, shares: number, netDebt: number, includeNetDebtBridge: boolean,
  dilutionRate: number, dilutionYears: number,
  bear: ScenarioInputs, base: ScenarioInputs, bull: ScenarioInputs,
): DcfResult {
  const includeBridge = includeNetDebtBridge && driver !== 'net_income'
  const run = (s: ScenarioInputs) => runScenario(startingValue, shares, netDebt, includeBridge, dilutionRate, dilutionYears, s)
  return {
    driver,
    net_debt_bridge_applied: includeBridge,
    bear: run(bear),
    base: run(base),
    bull: run(bull),
    sensitivity: sensitivityTable(startingValue, shares, netDebt, includeBridge, dilutionRate, dilutionYears, base),
  }
}
