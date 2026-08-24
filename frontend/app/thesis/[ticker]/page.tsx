'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'

// ── formatting helpers ──────────────────────────────────────────────────────

function fmtUsd(n: number | null | undefined, decimals = 2) {
  if (n == null || Number.isNaN(n)) return '—'
  return `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}
function fmtBig(n: number | null | undefined) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  return fmtUsd(n)
}
function fmtPct(n: number | null | undefined, signed = false) {
  if (n == null || Number.isNaN(n)) return '—'
  const v = (n * 100).toFixed(1)
  return signed && n > 0 ? `+${v}%` : `${v}%`
}
function fmtRatio(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—'
  return `${n.toFixed(2)}x`
}
function fmtShares(n: number | null | undefined) {
  if (n == null) return '—'
  return `${(n / 1e6).toFixed(0)}M`
}
function upsideColor(current: number | null, target: number | null) {
  if (current == null || target == null) return 'text-gray-500'
  return target > current ? 'text-emerald-400' : target < current ? 'text-red-400' : 'text-gray-400'
}

// ── rating system ────────────────────────────────────────────────────────
// Every metric gets a plain-language color: green = good, yellow = mixed,
// red = weak, gray = not enough data / informational only.

type Rating = 'good' | 'neutral' | 'bad' | 'na'

const RATING_DOT: Record<Rating, string> = {
  good: 'bg-emerald-400', neutral: 'bg-yellow-400', bad: 'bg-red-400', na: 'bg-gray-600',
}
const RATING_TEXT: Record<Rating, string> = {
  good: 'text-emerald-400', neutral: 'text-yellow-400', bad: 'text-red-400', na: 'text-gray-500',
}

function rateAbove(v: number | null | undefined, goodMin: number, neutralMin: number): Rating {
  if (v == null || Number.isNaN(v)) return 'na'
  return v >= goodMin ? 'good' : v >= neutralMin ? 'neutral' : 'bad'
}
function rateBelow(v: number | null | undefined, goodMax: number, neutralMax: number): Rating {
  if (v == null || Number.isNaN(v)) return 'na'
  return v <= goodMax ? 'good' : v <= neutralMax ? 'neutral' : 'bad'
}
function rateDilution(v: number | null | undefined): Rating {
  if (v == null || Number.isNaN(v)) return 'na'
  return v < 0 ? 'good' : v <= 0.02 ? 'neutral' : 'bad'
}

function verdict(ratings: Rating[]): { label: string; color: string } {
  const rated = ratings.filter((r) => r !== 'na')
  if (rated.length === 0) return { label: 'Not enough data', color: 'text-gray-500' }
  const good = rated.filter((r) => r === 'good').length
  const bad = rated.filter((r) => r === 'bad').length
  if (good >= rated.length - bad && good > bad) return { label: 'Strong', color: 'text-emerald-400' }
  if (bad > good) return { label: 'Weak', color: 'text-red-400' }
  return { label: 'Mixed', color: 'text-yellow-400' }
}

// ── small building blocks ───────────────────────────────────────────────────

function MetricRow({ label, value, rating, hint }: { label: string; value: string; rating: Rating; hint?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <div className="text-xs text-gray-300">{label}</div>
        {hint && <div className="text-[10px] text-gray-600 leading-snug mt-0.5">{hint}</div>}
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0 pt-0.5">
        <span className={`w-1.5 h-1.5 rounded-full ${RATING_DOT[rating]}`} />
        <span className={`text-xs font-semibold tabular-nums ${RATING_TEXT[rating]}`}>{value}</span>
      </div>
    </div>
  )
}

function SubsectionCard({ title, accent, description, verdictInfo, children }: {
  title: string; accent: string; description: string; verdictInfo: { label: string; color: string }; children: React.ReactNode
}) {
  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden" style={{ borderTopColor: accent, borderTopWidth: 2 }}>
      <div className="px-4 pt-3 pb-2 border-b border-border/50">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-100">{title}</h3>
          <span className={`text-[10px] font-semibold uppercase tracking-wider ${verdictInfo.color}`}>{verdictInfo.label}</span>
        </div>
        <p className="text-[10px] text-gray-600 mt-0.5">{description}</p>
      </div>
      <div className="px-4 py-1 divide-y divide-border/30">
        {children}
      </div>
    </div>
  )
}

function HistoryBars({ history, accent, unit }: { history: { fiscal_year_end: string; value: number }[]; accent: string; unit: 'big' | 'shares' }) {
  if (!history || history.length < 2) return null
  const values = history.map((h) => h.value)
  const min = Math.min(0, ...values)
  const max = Math.max(...values)
  const range = max - min || 1
  return (
    <div className="flex items-end gap-2 h-16 px-4 pb-3 pt-2">
      {history.map((h, i) => {
        const heightPct = Math.max(((h.value - min) / range) * 100, 4)
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
            <div className="w-full rounded-t" style={{ height: `${heightPct}%`, backgroundColor: accent, opacity: 0.6 }} />
            <span className="text-[9px] text-gray-600 whitespace-nowrap">{h.fiscal_year_end.slice(0, 4)}</span>
            <span className="text-[9px] text-gray-500 tabular-nums">{unit === 'big' ? fmtBig(h.value) : fmtShares(h.value)}</span>
          </div>
        )
      })}
    </div>
  )
}

function IncomeStatementChart({ data }: {
  data: { fiscal_year_end: string; revenue: number; gross_profit: number; operating_income: number; net_income: number }[]
}) {
  if (!data || data.length < 2) return null
  const series: { key: 'revenue' | 'gross_profit' | 'operating_income' | 'net_income'; label: string; color: string }[] = [
    { key: 'revenue', label: 'Revenue', color: '#60a5fa' },
    { key: 'gross_profit', label: 'Gross Profit', color: '#34d399' },
    { key: 'operating_income', label: 'Op. Income', color: '#fbbf24' },
    { key: 'net_income', label: 'Net Income', color: '#f472b6' },
  ]
  const allValues = data.flatMap((d) => series.map((s) => d[s.key]))
  const min = Math.min(0, ...allValues)
  const max = Math.max(...allValues)
  const range = max - min || 1
  return (
    <div className="px-4 pb-3 pt-2">
      <div className="flex items-end gap-3 h-28">
        {data.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
            <div className="w-full flex items-end justify-center gap-0.5 h-full">
              {series.map((s) => {
                const v = d[s.key]
                const heightPct = Math.max(((v - min) / range) * 100, 2)
                return (
                  <div
                    key={s.key}
                    className="flex-1 rounded-t"
                    style={{ height: `${heightPct}%`, backgroundColor: s.color, opacity: 0.8 }}
                    title={`${s.label} ${d.fiscal_year_end.slice(0, 4)}: ${fmtBig(v)}`}
                  />
                )
              })}
            </div>
            <span className="text-[9px] text-gray-600 whitespace-nowrap">{d.fiscal_year_end.slice(0, 4)}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 justify-center mt-2 flex-wrap">
        {series.map((s) => (
          <div key={s.key} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: s.color }} />
            <span className="text-[9px] text-gray-500">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Quality Screen ───────────────────────────────────────────────────────────

function QualityScreen({ f, onContinue }: { f: any; onContinue: () => void }) {
  const fcfMargin = f.revenue_ttm && f.free_cashflow != null ? f.free_cashflow / f.revenue_ttm : null
  const analystUpside = f.current_price && f.analyst_target_mean ? (f.analyst_target_mean / f.current_price) - 1 : null

  // Reliability
  const rGrowth = rateAbove(f.revenue_growth_yoy, 0.15, 0)
  const rCagr = rateAbove(f.revenue_cagr, 0.15, 0)
  const rCoverage = rateAbove(f.number_of_analysts, 15, 5)
  const rBeta = rateBelow(f.beta, 1.2, 1.8)

  // Profitability & efficiency
  const rGross = rateAbove(f.gross_margin, 0.5, 0.3)
  const rOperating = rateAbove(f.operating_margin, 0.2, 0.1)
  const rEbitda = rateAbove(f.ebitda_margin, 0.25, 0.12)
  const rProfit = rateAbove(f.profit_margin, 0.15, 0.05)
  const rFcf = rateAbove(fcfMargin, 0.15, 0.05)
  const rRoe = rateAbove(f.return_on_equity, 0.20, 0.10)
  const rRoa = rateAbove(f.return_on_assets, 0.10, 0.05)

  // Debt & liquidity
  const rDebtToEquity = rateBelow(f.debt_to_equity_pct, 40, 100)
  const rCurrentRatio = rateAbove(f.current_ratio, 1.5, 1.0)
  const rQuickRatio = rateAbove(f.quick_ratio, 1.0, 0.7)
  const rNetDebtEbitda = rateBelow(f.net_debt_to_ebitda, 1, 3)
  const rInterestCoverage = f.interest_coverage == null ? 'good' : rateAbove(f.interest_coverage, 8, 3)

  // Dilution
  const rDilutionYoy = rateDilution(f.shares_yoy)
  const rDilutionCagr = rateDilution(f.shares_cagr)

  // Valuation
  const rPeg = rateBelow(f.peg_ratio, 1, 2)
  const rForwardPe = rateBelow(f.forward_pe, 20, 35)
  const rEvEbitda = rateBelow(f.ev_to_ebitda, 15, 25)
  const rPs = rateBelow(f.price_to_sales, 5, 10)
  const rPb = rateBelow(f.price_to_book, 5, 10)
  const rUpside = rateAbove(analystUpside, 0.15, 0)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">

        <SubsectionCard
          title="Is the business reliable?"
          accent="#3b82f6"
          description="Consistent, well-understood growth — not lumpy, not a black box."
          verdictInfo={verdict([rGrowth, rCagr, rCoverage, rBeta])}
        >
          <MetricRow label="Revenue growth (YoY)" value={fmtPct(f.revenue_growth_yoy, true)} rating={rGrowth} hint="How fast sales grew over the last year" />
          <MetricRow label={`Revenue CAGR (${f.revenue_history?.length ? f.revenue_history.length - 1 : '—'}yr)`} value={fmtPct(f.revenue_cagr, true)} rating={rCagr} hint="Compounded growth across available history — smooths one-off spikes" />
          <MetricRow label="Analyst coverage" value={f.number_of_analysts != null ? `${f.number_of_analysts} analysts` : '—'} rating={rCoverage} hint="More coverage generally means more reliable consensus estimates" />
          <MetricRow label="Price volatility (beta)" value={f.beta != null ? f.beta.toFixed(2) : '—'} rating={rBeta} hint="Swings vs. the market — 1.0 = same as market" />
          <IncomeStatementChart data={f.income_statement_history} />
        </SubsectionCard>

        <SubsectionCard
          title="Is the business profitable and efficient?"
          accent="#34d399"
          description="How much of every sales dollar turns into real profit and cash."
          verdictInfo={verdict([rGross, rOperating, rEbitda, rProfit, rFcf, rRoe, rRoa])}
        >
          <MetricRow label="Gross margin" value={fmtPct(f.gross_margin)} rating={rGross} hint="Revenue left after direct cost of goods — pricing power" />
          <MetricRow label="Operating margin" value={fmtPct(f.operating_margin)} rating={rOperating} hint="Profit after running the business, before interest/tax" />
          <MetricRow label="EBITDA margin" value={fmtPct(f.ebitda_margin)} rating={rEbitda} hint="Cash profitability before non-cash charges" />
          <MetricRow label="Net profit margin" value={fmtPct(f.profit_margin)} rating={rProfit} hint="What's left for shareholders after everything" />
          <MetricRow label="FCF margin" value={fmtPct(fcfMargin)} rating={rFcf} hint="Actual cash generated per dollar of revenue — hardest to fake" />
          <MetricRow label="Return on equity" value={fmtPct(f.return_on_equity)} rating={rRoe} hint="Profit generated per dollar of shareholder capital" />
          <MetricRow label="Return on assets" value={fmtPct(f.return_on_assets)} rating={rRoa} hint="Profit generated per dollar of total assets" />
        </SubsectionCard>

        <SubsectionCard
          title="Is the balance sheet healthy?"
          accent="#fb923c"
          description="How much debt the business carries, and how easily it could cover it."
          verdictInfo={verdict([rDebtToEquity, rCurrentRatio, rQuickRatio, rNetDebtEbitda, rInterestCoverage])}
        >
          <MetricRow label="Net debt (cash if negative)" value={fmtBig(f.net_debt)} rating="na" hint="Total debt minus cash on hand" />
          <MetricRow label="Net debt / EBITDA" value={fmtRatio(f.net_debt_to_ebitda)} rating={rNetDebtEbitda} hint="Years of cash flow needed to pay off net debt" />
          <MetricRow label="Debt / Equity" value={f.debt_to_equity_pct != null ? `${f.debt_to_equity_pct.toFixed(1)}%` : '—'} rating={rDebtToEquity} hint="Debt as a share of shareholder equity" />
          <MetricRow label="Current ratio" value={fmtRatio(f.current_ratio)} rating={rCurrentRatio} hint="Short-term assets vs. short-term liabilities — above 1x covers them" />
          <MetricRow label="Quick ratio" value={fmtRatio(f.quick_ratio)} rating={rQuickRatio} hint="Same, excluding inventory — a stricter cash-coverage test" />
          <MetricRow label="Interest coverage" value={f.interest_coverage != null ? fmtRatio(f.interest_coverage) : '— (negligible debt)'} rating={rInterestCoverage} hint="EBIT vs. interest expense — how easily profit covers interest payments" />
        </SubsectionCard>

        <SubsectionCard
          title="Is the business diluting at a fast pace?"
          accent="#f59e0b"
          description="Is your ownership stake shrinking (dilution) or growing (buybacks)?"
          verdictInfo={verdict([rDilutionYoy, rDilutionCagr])}
        >
          <MetricRow label="Shares outstanding (YoY)" value={fmtPct(f.shares_yoy, true)} rating={rDilutionYoy} hint="Negative = buybacks shrinking share count, positive = dilution" />
          <MetricRow label={`Shares CAGR (${f.shares_history?.length ? f.shares_history.length - 1 : '—'}yr)`} value={fmtPct(f.shares_cagr, true)} rating={rDilutionCagr} hint="Trend in share count over available history" />
          <MetricRow label="Insider ownership" value={fmtPct(f.insider_pct)} rating="na" hint="% held by company insiders — informational" />
          <MetricRow label="Institutional ownership" value={fmtPct(f.institution_pct)} rating="na" hint="% held by funds/institutions — informational" />
          <HistoryBars history={f.shares_history} accent="#f59e0b" unit="shares" />
        </SubsectionCard>

        <SubsectionCard
          title="Are the ratios cheap or expensive?"
          accent="#a78bfa"
          description="Generic heuristics, not sector-adjusted — read alongside the growth story."
          verdictInfo={verdict([rPeg, rForwardPe, rEvEbitda, rPs, rPb, rUpside])}
        >
          <MetricRow label="PEG ratio" value={f.peg_ratio != null ? f.peg_ratio.toFixed(2) : '—'} rating={rPeg} hint="P/E adjusted for growth — the cleanest cheap-vs-expensive signal" />
          <MetricRow label="Forward P/E" value={fmtRatio(f.forward_pe)} rating={rForwardPe} hint="Price vs. next year's expected earnings" />
          <MetricRow label="Trailing P/E" value={fmtRatio(f.trailing_pe)} rating="na" hint="Price vs. last 12 months' earnings" />
          <MetricRow label="EV / EBITDA" value={fmtRatio(f.ev_to_ebitda)} rating={rEvEbitda} hint="Capital-structure-neutral valuation multiple" />
          <MetricRow label="Price / Sales" value={fmtRatio(f.price_to_sales)} rating={rPs} hint="Useful when earnings are thin or negative" />
          <MetricRow label="Price / Book" value={fmtRatio(f.price_to_book)} rating={rPb} hint="Price vs. net asset value" />
          <MetricRow label="Analyst target upside" value={fmtPct(analystUpside, true)} rating={rUpside} hint={`Current ${fmtUsd(f.current_price)} vs. mean target ${fmtUsd(f.analyst_target_mean)}`} />
        </SubsectionCard>

      </div>

      <button
        onClick={onContinue}
        className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors"
      >
        Continue to Thesis →
      </button>
    </div>
  )
}

// ── Thesis stage (placeholder — built next) ─────────────────────────────────

function ThesisStage({ onBack, onSkipToDcf }: { onBack: () => void; onSkipToDcf: () => void }) {
  const questions = [
    'What is the demand?',
    'What is the moat?',
    'Is the moat widening or narrowing?',
    'Do the numbers complete the story?',
    'What stage is the company at — Growth, Stabilization, or Mature?',
  ]
  return (
    <div className="space-y-4 max-w-2xl">
      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-100 mb-1">Thesis Builder — coming next</h3>
        <p className="text-xs text-gray-500 mb-3">
          Built on top of the Quality Screen above. It will answer a short set of business
          questions and roll them into a 2-line growth thesis.
        </p>
        <ul className="space-y-1.5">
          {questions.map((q) => (
            <li key={q} className="text-xs text-gray-400 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-gray-600 flex-shrink-0" />
              {q}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex gap-2">
        <button onClick={onBack} className="px-4 py-2 rounded-lg text-sm font-medium bg-white/5 text-gray-400 hover:bg-white/10 transition-colors">
          ← Back to Quality Screen
        </button>
        <button onClick={onSkipToDcf} className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors">
          Skip to DCF →
        </button>
      </div>
    </div>
  )
}

// ── DCF stage (existing scenario builder) ───────────────────────────────────

interface Scenario {
  growth_start: number
  growth_end: number
  fcf_margin: number
  wacc: number
  terminal_growth: number
}

function defaultScenarios(f: any): { bear: Scenario; base: Scenario; bull: Scenario } {
  const baseGrowth = f?.revenue_growth_yoy ?? 0.10
  const fcfMargin = f?.revenue_ttm && f?.free_cashflow ? f.free_cashflow / f.revenue_ttm : 0.15
  return {
    bear: { growth_start: Math.max(baseGrowth - 0.10, -0.05), growth_end: 0.02, fcf_margin: Math.max(fcfMargin - 0.08, 0.02), wacc: 0.11, terminal_growth: 0.02 },
    base: { growth_start: baseGrowth, growth_end: 0.05, fcf_margin: fcfMargin, wacc: 0.09, terminal_growth: 0.025 },
    bull: { growth_start: baseGrowth + 0.10, growth_end: 0.08, fcf_margin: Math.min(fcfMargin + 0.08, 0.5), wacc: 0.08, terminal_growth: 0.03 },
  }
}

function ScenarioForm({ label, color, value, onChange }: {
  label: string; color: string; value: Scenario; onChange: (s: Scenario) => void
}) {
  const field = (key: keyof Scenario, fieldLabel: string, step = 0.01) => (
    <label className="block">
      <span className="text-[10px] text-gray-600">{fieldLabel}</span>
      <input
        type="number"
        step={step}
        value={value[key]}
        onChange={(e) => onChange({ ...value, [key]: parseFloat(e.target.value) || 0 })}
        className="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-gray-100 mt-0.5 focus:outline-none focus:border-blue-500"
      />
    </label>
  )
  return (
    <div className="bg-card border border-border rounded-xl p-3 space-y-2" style={{ borderTopColor: color, borderTopWidth: 2 }}>
      <div className={`text-xs font-semibold ${color === '#f87171' ? 'text-red-400' : color === '#34d399' ? 'text-emerald-400' : 'text-gray-300'}`}>{label}</div>
      {field('growth_start', 'Y1 growth')}
      {field('growth_end', 'Growth by final year')}
      {field('fcf_margin', 'FCF margin')}
      {field('wacc', 'WACC')}
      {field('terminal_growth', 'Terminal growth')}
    </div>
  )
}

function SensitivityTable({ sens, current }: { sens: any; current: number | null }) {
  if (!sens) return null
  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse">
        <thead>
          <tr>
            <th className="px-2 py-1 text-gray-600"></th>
            {sens.terminal_growth_axis.map((tg: number, i: number) => (
              <th key={i} className="px-2 py-1 text-gray-500 font-normal">{fmtPct(tg)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sens.wacc_axis.map((w: number, ri: number) => (
            <tr key={ri}>
              <td className="px-2 py-1 text-gray-500 whitespace-nowrap">WACC {fmtPct(w)}</td>
              {sens.grid[ri].map((price: number | null, ci: number) => (
                <td key={ci} className={`px-2 py-1 text-center tabular-nums ${upsideColor(current, price)}`}>
                  {price != null ? fmtUsd(price, 0) : '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Stat({ label, value, color, bold }: { label: string; value: string; color?: string; bold?: boolean }) {
  return (
    <div className="bg-card border border-border rounded-xl p-3">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-sm tabular-nums ${bold ? 'font-bold text-base' : 'font-semibold'} ${color ?? 'text-gray-100'}`}>{value}</p>
    </div>
  )
}

function CommentaryCard({ label, text, color }: { label: string; text: string; color: string }) {
  return (
    <div className="bg-card border border-border rounded-xl p-3">
      <div className={`text-xs font-semibold mb-1 ${color}`}>{label}</div>
      <p className="text-xs text-gray-400 leading-relaxed">{text}</p>
    </div>
  )
}

function DcfStage({ ticker, fundamentals, onBack }: { ticker: string; fundamentals: any; onBack: () => void }) {
  const [scenarios, setScenarios] = useState(() => defaultScenarios(fundamentals))
  const [years, setYears] = useState(5)
  const [history, setHistory] = useState<any[]>([])
  const [viewingRun, setViewingRun] = useState<any>(null)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)

  useEffect(() => {
    api.thesis.history(ticker).then(setHistory).catch(() => setHistory([]))
  }, [ticker])

  async function handleGenerate() {
    setGenerating(true)
    setGenError(null)
    try {
      const run = await api.thesis.generate(ticker, { years, bear: scenarios.bear, base: scenarios.base, bull: scenarios.bull })
      setResult(run)
      setViewingRun(null)
      api.thesis.history(ticker).then(setHistory).catch(() => {})
    } catch (e: any) {
      setGenError(String(e.message || e))
    } finally {
      setGenerating(false)
    }
  }

  async function loadRun(id: number) {
    const run = await api.thesis.run(id)
    setViewingRun(run)
    setResult(null)
  }

  const displayed = viewingRun ?? result
  const displayedDcf = displayed?.dcf_outputs_json ?? null

  return (
    <div className="space-y-6">
      <button onClick={onBack} className="text-xs text-blue-400 hover:underline">← Back to Thesis</button>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-[10px] text-gray-600 uppercase tracking-wider">DCF Assumptions</h2>
          <label className="text-[10px] text-gray-600 flex items-center gap-1.5">
            Projection years
            <input
              type="number" min={3} max={10} value={years}
              onChange={(e) => setYears(parseInt(e.target.value) || 5)}
              className="w-14 bg-surface border border-border rounded px-1.5 py-0.5 text-xs text-gray-100"
            />
          </label>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <ScenarioForm label="Bear" color="#f87171" value={scenarios.bear} onChange={(s) => setScenarios({ ...scenarios, bear: s })} />
          <ScenarioForm label="Base" color="#9ca3af" value={scenarios.base} onChange={(s) => setScenarios({ ...scenarios, base: s })} />
          <ScenarioForm label="Bull" color="#34d399" value={scenarios.bull} onChange={(s) => setScenarios({ ...scenarios, bull: s })} />
        </div>

        <button
          onClick={handleGenerate}
          disabled={generating}
          className="mt-3 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors disabled:opacity-40"
        >
          {generating ? 'Generating…' : 'Generate Thesis'}
        </button>
        {genError && <p className="text-xs text-red-400 mt-2">{genError}</p>}
      </div>

      {displayed && displayedDcf && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-[10px] text-gray-600 uppercase tracking-wider">
              {viewingRun ? `Saved run · ${new Date(viewingRun.created_at).toLocaleString()}` : 'Result'}
            </h2>
            {viewingRun && (
              <button onClick={() => setViewingRun(null)} className="text-[10px] text-blue-400 hover:underline">Back to current</button>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Stat label="Bear FV" value={fmtUsd(displayed.fair_value_bear)} color={upsideColor(displayed.current_price, displayed.fair_value_bear)} />
            <Stat label="Base FV" value={fmtUsd(displayed.fair_value_base)} color={upsideColor(displayed.current_price, displayed.fair_value_base)} />
            <Stat label="Bull FV" value={fmtUsd(displayed.fair_value_bull)} color={upsideColor(displayed.current_price, displayed.fair_value_bull)} />
            <Stat label="Target Price" value={fmtUsd(displayed.target_price)} color={upsideColor(displayed.current_price, displayed.target_price)} bold />
          </div>

          {displayed.thesis_text && (
            <div className="bg-card border border-border rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-300 mb-1.5">Thesis</h3>
              <p className="text-sm text-gray-300 leading-relaxed">{displayed.thesis_text}</p>
            </div>
          )}

          {displayedDcf.scenario_commentary && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <CommentaryCard label="Bear" text={displayedDcf.scenario_commentary.bear} color="text-red-400" />
              <CommentaryCard label="Base" text={displayedDcf.scenario_commentary.base} color="text-gray-300" />
              <CommentaryCard label="Bull" text={displayedDcf.scenario_commentary.bull} color="text-emerald-400" />
            </div>
          )}

          {displayed.risks_json && (
            <div className="bg-card border border-border rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-300 mb-2">Top Risks</h3>
              <ul className="space-y-2">
                {displayed.risks_json.map((r: any, i: number) => (
                  <li key={i} className="text-sm">
                    <span className="text-yellow-400 font-medium">{r.title}</span>
                    <span className="text-gray-400"> — {r.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {displayedDcf.sensitivity && (
            <div className="bg-card border border-border rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-300 mb-2">Sensitivity — Implied Price (Base Case)</h3>
              <SensitivityTable sens={displayedDcf.sensitivity} current={displayed.current_price} />
            </div>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div>
          <h2 className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">History</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden divide-y divide-border/50">
            {history.map((h) => (
              <button
                key={h.id}
                onClick={() => loadRun(h.id)}
                className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-white/5 transition-colors text-left"
              >
                <span className="text-xs text-gray-400">{new Date(h.created_at).toLocaleString()}</span>
                <span className="text-xs text-gray-300 tabular-nums">
                  Target {fmtUsd(h.target_price)} · Price then {fmtUsd(h.current_price)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Stage stepper ────────────────────────────────────────────────────────────

type Stage = 'quality' | 'thesis' | 'dcf'
const STAGES: { key: Stage; label: string }[] = [
  { key: 'quality', label: '1. Quality Screen' },
  { key: 'thesis', label: '2. Thesis' },
  { key: 'dcf', label: '3. DCF' },
]

function StageStepper({ stage, unlocked, onSelect }: { stage: Stage; unlocked: Stage[]; onSelect: (s: Stage) => void }) {
  return (
    <div className="flex gap-1.5">
      {STAGES.map((s) => {
        const isActive = s.key === stage
        const isUnlocked = unlocked.includes(s.key)
        return (
          <button
            key={s.key}
            disabled={!isUnlocked}
            onClick={() => onSelect(s.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              isActive
                ? 'bg-blue-600/20 text-blue-400'
                : isUnlocked
                  ? 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                  : 'text-gray-700 cursor-not-allowed'
            }`}
          >
            {s.label}
          </button>
        )
      })}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function ThesisTickerPage() {
  const params = useParams()
  const ticker = String(params.ticker).toUpperCase()

  const [fundamentals, setFundamentals] = useState<any>(null)
  const [fundamentalsError, setFundamentalsError] = useState<string | null>(null)
  const [loadingFundamentals, setLoadingFundamentals] = useState(true)
  const [stage, setStage] = useState<Stage>('quality')
  const [unlocked, setUnlocked] = useState<Stage[]>(['quality'])

  useEffect(() => {
    setLoadingFundamentals(true)
    api.thesis.fetchFundamentals(ticker)
      .then((f) => setFundamentals(f))
      .catch((e) => setFundamentalsError(String(e.message || e)))
      .finally(() => setLoadingFundamentals(false))
  }, [ticker])

  function goTo(s: Stage) {
    setUnlocked((prev) => (prev.includes(s) ? prev : [...prev, s]))
    setStage(s)
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100 font-mono">{ticker}</h1>
          <p className="text-xs text-gray-600 mt-0.5">{fundamentals?.long_name ?? (loadingFundamentals ? 'Loading fundamentals…' : '')}</p>
        </div>
        {fundamentals?.current_price != null && (
          <div className="text-right">
            <div className="text-xl font-semibold text-gray-100 tabular-nums">{fmtUsd(fundamentals.current_price)}</div>
            <div className="text-[10px] text-gray-600">Current price</div>
          </div>
        )}
      </div>

      {fundamentalsError && (
        <div className="bg-red-950/30 border border-red-900 rounded-lg px-4 py-3 text-xs text-red-400">
          {fundamentalsError}
        </div>
      )}

      {loadingFundamentals && (
        <div className="text-xs text-gray-600 py-12 text-center">Pulling fundamentals…</div>
      )}

      {fundamentals && (
        <>
          <StageStepper stage={stage} unlocked={unlocked} onSelect={goTo} />

          {stage === 'quality' && <QualityScreen f={fundamentals} onContinue={() => goTo('thesis')} />}
          {stage === 'thesis' && <ThesisStage onBack={() => goTo('quality')} onSkipToDcf={() => goTo('dcf')} />}
          {stage === 'dcf' && <DcfStage ticker={ticker} fundamentals={fundamentals} onBack={() => goTo('thesis')} />}
        </>
      )}
    </div>
  )
}
