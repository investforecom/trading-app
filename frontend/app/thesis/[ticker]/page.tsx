'use client'

import { useState, useEffect, useMemo } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'
import { runDcf, runScenario, impliedMultipleFromGordon, impliedGrowthFromMultiple } from '@/lib/dcf'

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
function rateRelative(current: number | null | undefined, benchmark: number | null | undefined): Rating {
  if (current == null || benchmark == null || benchmark <= 0) return 'na'
  const ratio = current / benchmark
  return ratio <= 0.85 ? 'good' : ratio >= 1.15 ? 'bad' : 'neutral'
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

interface ValuationRow {
  label: string
  hint?: string
  value: string
  rating: Rating
  ownHistory?: string
  sectorMedian?: string
}

function ValuationTable({ rows, peerCount }: { rows: ValuationRow[]; peerCount?: number }) {
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-[9px] text-gray-600 uppercase tracking-wider">
            <th className="text-left font-normal py-1 px-1">Metric</th>
            <th className="text-right font-normal py-1 px-1">Value</th>
            <th className="text-right font-normal py-1 px-1">Own History</th>
            <th className="text-right font-normal py-1 px-1">{peerCount ? `Sector (${peerCount})` : 'Sector'}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          {rows.map((r) => (
            <tr key={r.label}>
              <td className="py-1.5 px-1 text-gray-300 align-top">
                <div className="whitespace-nowrap">{r.label}</div>
                {r.hint && <div className="text-[10px] text-gray-600 leading-snug mt-0.5 whitespace-normal">{r.hint}</div>}
              </td>
              <td className={`py-1.5 px-1 text-right font-semibold tabular-nums whitespace-nowrap align-top ${RATING_TEXT[r.rating]}`}>{r.value}</td>
              <td className="py-1.5 px-1 text-right text-gray-500 tabular-nums whitespace-nowrap align-top">{r.ownHistory ?? '—'}</td>
              <td className="py-1.5 px-1 text-right text-gray-500 tabular-nums whitespace-nowrap align-top">{r.sectorMedian ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
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

interface ChartSeries { key: string; label: string; color: string }

function GroupedBarChart({ data, series }: { data: Record<string, any>[]; series: ChartSeries[] }) {
  if (!data || data.length < 2) return null
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

  // Reliability (income statement growth)
  const rGrowth = rateAbove(f.revenue_growth_yoy, 0.15, 0)
  const rCagr = rateAbove(f.revenue_cagr, 0.15, 0)
  const rGrossProfitYoy = rateAbove(f.gross_profit_yoy, 0.15, 0)
  const rGrossProfitCagr = rateAbove(f.gross_profit_cagr, 0.15, 0)
  const rOperatingIncomeYoy = rateAbove(f.operating_income_yoy, 0.15, 0)
  const rOperatingIncomeCagr = rateAbove(f.operating_income_cagr, 0.15, 0)
  const rNetIncomeYoy = rateAbove(f.net_income_yoy, 0.15, 0)
  const rNetIncomeCagr = rateAbove(f.net_income_cagr, 0.15, 0)

  // Cash conversion
  const rOcfYoy = rateAbove(f.operating_cashflow_yoy, 0.15, 0)
  const rOcfCagr = rateAbove(f.operating_cashflow_cagr, 0.15, 0)
  const rFcfYoy = rateAbove(f.fcf_yoy, 0.15, 0)
  const rFcfCagr = rateAbove(f.fcf_cagr, 0.15, 0)

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

  // Valuation — prefer sector-peer median, fall back to the company's own
  // trading history, and fall back further to a generic heuristic when
  // neither benchmark is available.
  const peer = f.peer_benchmark ?? {}
  const peBenchmark = peer.median_pe ?? f.own_pe_median
  const psBenchmark = peer.median_ps ?? f.own_ps_median
  const pbBenchmark = peer.median_pb ?? f.own_pb_median

  const rPeg = rateBelow(f.peg_ratio, 1, 2)
  const rForwardPe = peer.median_forward_pe != null ? rateRelative(f.forward_pe, peer.median_forward_pe) : rateBelow(f.forward_pe, 20, 35)
  const rTrailingPe = peBenchmark != null ? rateRelative(f.trailing_pe, peBenchmark) : 'na'
  const rEvEbitda = peer.median_ev_ebitda != null ? rateRelative(f.ev_to_ebitda, peer.median_ev_ebitda) : rateBelow(f.ev_to_ebitda, 15, 25)
  const rPs = psBenchmark != null ? rateRelative(f.price_to_sales, psBenchmark) : rateBelow(f.price_to_sales, 5, 10)
  const rPb = pbBenchmark != null ? rateRelative(f.price_to_book, pbBenchmark) : rateBelow(f.price_to_book, 5, 10)
  const rUpside = rateAbove(analystUpside, 0.15, 0)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">

        <SubsectionCard
          title="Is the business reliable?"
          accent="#3b82f6"
          description="Consistent, well-understood growth across the whole income statement — not lumpy, not a black box."
          verdictInfo={verdict([rGrowth, rCagr, rGrossProfitYoy, rGrossProfitCagr, rOperatingIncomeYoy, rOperatingIncomeCagr, rNetIncomeYoy, rNetIncomeCagr])}
        >
          <MetricRow label="Revenue growth (YoY)" value={fmtPct(f.revenue_growth_yoy, true)} rating={rGrowth} hint={`${fmtBig(f.revenue_ttm)} TTM — how fast sales grew over the last year`} />
          <MetricRow label={`Revenue CAGR (${f.revenue_history?.length ? f.revenue_history.length - 1 : '—'}yr)`} value={fmtPct(f.revenue_cagr, true)} rating={rCagr} hint="Compounded growth across available history — smooths one-off spikes" />
          <MetricRow label="Gross Profit YoY" value={fmtPct(f.gross_profit_yoy, true)} rating={rGrossProfitYoy} hint={`${fmtBig(f.gross_profit_ttm)} TTM — is pricing power keeping pace with revenue right now?`} />
          <MetricRow label="Gross Profit CAGR" value={fmtPct(f.gross_profit_cagr, true)} rating={rGrossProfitCagr} hint="Multi-year trend — compare against YoY to see if it's accelerating or fading" />
          <MetricRow label="Op Income YoY" value={fmtPct(f.operating_income_yoy, true)} rating={rOperatingIncomeYoy} hint={`${fmtBig(f.operating_income_ttm)} TTM — is operating leverage improving right now?`} />
          <MetricRow label="Op Income CAGR" value={fmtPct(f.operating_income_cagr, true)} rating={rOperatingIncomeCagr} hint="Multi-year trend — compare against YoY to see if it's accelerating or fading" />
          <MetricRow label="Net Income YoY" value={fmtPct(f.net_income_yoy, true)} rating={rNetIncomeYoy} hint={`${fmtBig(f.net_income_ttm)} TTM — bottom-line growth over the last year`} />
          <MetricRow label="Net Income CAGR" value={fmtPct(f.net_income_cagr, true)} rating={rNetIncomeCagr} hint="Multi-year trend — compare against YoY to see if it's accelerating or fading" />
          <GroupedBarChart data={f.income_statement_history} series={[
            { key: 'revenue', label: 'Revenue', color: '#60a5fa' },
            { key: 'gross_profit', label: 'Gross Profit', color: '#34d399' },
            { key: 'operating_income', label: 'Op. Income', color: '#fbbf24' },
            { key: 'net_income', label: 'Net Income', color: '#f472b6' },
          ]} />
        </SubsectionCard>

        <SubsectionCard
          title="Does the business convert profit into cash?"
          accent="#22d3ee"
          description="Reported profit means little if it never shows up as cash — this catches the gap."
          verdictInfo={verdict([rOcfYoy, rOcfCagr, rFcfYoy, rFcfCagr])}
        >
          <MetricRow label="Op Cash Flow YoY" value={fmtPct(f.operating_cashflow_yoy, true)} rating={rOcfYoy} hint={`${fmtBig(f.operating_cashflow_ttm)} TTM — is cash generation growing right now?`} />
          <MetricRow label="Op Cash Flow CAGR" value={fmtPct(f.operating_cashflow_cagr, true)} rating={rOcfCagr} hint="Multi-year trend — compare against YoY to see if it's accelerating or fading" />
          <MetricRow label="Capex YoY" value={fmtPct(f.capex_yoy, true)} rating="na" hint={`${fmtBig(f.capex_ttm)} most recent FY (no true TTM figure available) — faster isn't inherently good or bad, depends on what it's funding`} />
          <MetricRow label="Capex CAGR" value={fmtPct(f.capex_cagr, true)} rating="na" hint="Multi-year reinvestment trend — informational, not graded" />
          <MetricRow label="FCF YoY" value={fmtPct(f.fcf_yoy, true)} rating={rFcfYoy} hint={`${fmtBig(f.free_cashflow)} TTM — hardest metric to fake, the cleanest cash-conversion signal`} />
          <MetricRow label="FCF CAGR" value={fmtPct(f.fcf_cagr, true)} rating={rFcfCagr} hint="Multi-year trend — compare against YoY to see if it's accelerating or fading" />
          <GroupedBarChart data={f.cash_flow_history} series={[
            { key: 'operating_cash_flow', label: 'Op. Cash Flow', color: '#60a5fa' },
            { key: 'capex', label: 'Capex', color: '#f87171' },
            { key: 'fcf', label: 'FCF', color: '#34d399' },
          ]} />
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
          description={
            peer.peer_count
              ? `Benchmarked against ${peer.peer_count} sector peers and the company's own trading history.`
              : 'Benchmarked against the company\'s own trading history where available; otherwise a generic heuristic.'
          }
          verdictInfo={verdict([rPeg, rForwardPe, rTrailingPe, rEvEbitda, rPs, rPb, rUpside])}
        >
          <ValuationTable
            peerCount={peer.peer_count}
            rows={[
              { label: 'PEG ratio', hint: 'P/E adjusted for growth — the cleanest cheap-vs-expensive signal', value: f.peg_ratio != null ? f.peg_ratio.toFixed(2) : '—', rating: rPeg, sectorMedian: peer.median_peg?.toFixed(2) },
              { label: 'Forward P/E', hint: "Price vs. next year's expected earnings", value: fmtRatio(f.forward_pe), rating: rForwardPe, sectorMedian: peer.median_forward_pe != null ? fmtRatio(peer.median_forward_pe) : undefined },
              { label: 'Trailing P/E', hint: "Price vs. last 12 months' earnings", value: fmtRatio(f.trailing_pe), rating: rTrailingPe, ownHistory: f.own_pe_median != null ? fmtRatio(f.own_pe_median) : undefined, sectorMedian: peer.median_pe != null ? fmtRatio(peer.median_pe) : undefined },
              { label: 'EV / EBITDA', hint: 'Capital-structure-neutral valuation multiple', value: fmtRatio(f.ev_to_ebitda), rating: rEvEbitda, sectorMedian: peer.median_ev_ebitda != null ? fmtRatio(peer.median_ev_ebitda) : undefined },
              { label: 'Price / Sales', hint: 'Useful when earnings are thin or negative', value: fmtRatio(f.price_to_sales), rating: rPs, ownHistory: f.own_ps_median != null ? fmtRatio(f.own_ps_median) : undefined, sectorMedian: peer.median_ps != null ? fmtRatio(peer.median_ps) : undefined },
              { label: 'Price / Book', hint: 'Price vs. net asset value', value: fmtRatio(f.price_to_book), rating: rPb, ownHistory: f.own_pb_median != null ? fmtRatio(f.own_pb_median) : undefined, sectorMedian: peer.median_pb != null ? fmtRatio(peer.median_pb) : undefined },
            ]}
          />
          <MetricRow label="Analyst target upside" value={fmtPct(analystUpside, true)} rating={rUpside} hint={`Current ${fmtUsd(f.current_price)} vs. mean target ${fmtUsd(f.analyst_target_mean)}`} />
          {peer.peers?.length > 0 && (
            <div className="py-1.5 text-[10px] text-gray-600">Sector peers: {peer.peers.join(', ')}</div>
          )}
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

const STAGE_BADGE_COLOR: Record<string, string> = {
  Growth: 'text-emerald-400 bg-emerald-400/10',
  Stabilization: 'text-yellow-400 bg-yellow-400/10',
  Mature: 'text-gray-400 bg-gray-400/10',
}
const MOAT_TREND_COLOR: Record<string, string> = {
  Widening: 'text-emerald-400', Stable: 'text-yellow-400', Narrowing: 'text-red-400',
}

function ThesisQaCard({ label, text, accent }: { label: string; text: string; accent: string }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4" style={{ borderLeftColor: accent, borderLeftWidth: 2 }}>
      <h4 className="text-xs font-semibold text-gray-300 mb-1.5">{label}</h4>
      <p className="text-sm text-gray-400 leading-relaxed">{text}</p>
    </div>
  )
}

function ThesisStage({ ticker, fundamentals, onBack, onSkipToDcf, onThesisChange }: {
  ticker: string; fundamentals: any; onBack: () => void; onSkipToDcf: () => void; onThesisChange: (qa: any) => void
}) {
  const [qa, setQa] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [viewingSnapshot, setViewingSnapshot] = useState<any>(null)

  useEffect(() => {
    setLoading(true)
    setViewingSnapshot(null)
    api.thesis.thesisQa(ticker).then(setQa).catch((e) => setError(String(e.message || e))).finally(() => setLoading(false))
    api.thesis.thesisQaHistory(ticker).then(setHistory).catch(() => setHistory([]))
  }, [ticker])

  useEffect(() => { onThesisChange(qa) }, [qa])

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    try {
      const result = await api.thesis.generateThesisQa(ticker)
      setQa(result)
      setViewingSnapshot(null)
      api.thesis.thesisQaHistory(ticker).then(setHistory).catch(() => {})
    } catch (e: any) {
      setError(String(e.message || e))
    } finally {
      setGenerating(false)
    }
  }

  async function loadSnapshot(id: number) {
    const snap = await api.thesis.thesisQaSnapshot(ticker, id)
    setViewingSnapshot(snap)
  }

  const displayed = viewingSnapshot ?? qa
  const stale = qa?._based_on_fetched_at && fundamentals?._cached_at && qa._based_on_fetched_at < fundamentals._cached_at

  return (
    <div className="space-y-4 max-w-3xl">
      {loading && <div className="text-xs text-gray-600 py-12 text-center">Loading thesis…</div>}

      {!loading && !qa && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-100 mb-1">No thesis generated yet</h3>
          <p className="text-xs text-gray-500 mb-3">
            Answers demand, moat, moat direction, and growth stage — grounded in the Quality
            Screen fundamentals above, with a bounded web search to fill in anything the
            numbers alone can't answer (e.g. a recent 10-Q disclosure).
          </p>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors disabled:opacity-40"
          >
            {generating ? 'Generating…' : 'Generate Thesis'}
          </button>
        </div>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}

      {displayed && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded ${STAGE_BADGE_COLOR[displayed.stage] ?? 'text-gray-400 bg-gray-400/10'}`}>
                {displayed.stage}
              </span>
              <span className="text-[10px] text-gray-600">
                {viewingSnapshot ? `Snapshot from ${new Date(viewingSnapshot._generated_at).toLocaleString()}` : displayed._generated_at ? `Generated ${new Date(displayed._generated_at).toLocaleString()}` : null}
              </span>
            </div>
            {viewingSnapshot ? (
              <button onClick={() => setViewingSnapshot(null)} className="text-[10px] text-blue-400 hover:underline">Back to current</button>
            ) : (
              <button onClick={handleGenerate} disabled={generating} className="text-[10px] text-blue-400 hover:underline disabled:opacity-40">
                {generating ? 'Regenerating…' : 'Regenerate'}
              </button>
            )}
          </div>

          {!viewingSnapshot && stale && (
            <div className="bg-yellow-950/20 border border-yellow-900/50 rounded-lg px-3 py-2 text-[10px] text-yellow-500">
              Fundamentals were refreshed after this thesis was generated — consider regenerating.
            </div>
          )}

          <div className="bg-card border border-border rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-300 mb-1.5">Thesis</h3>
            <p className="text-sm text-gray-100 leading-relaxed">{displayed.thesis_text}</p>
            <p className="text-[10px] text-gray-600 mt-2">{displayed.stage_reason}</p>
            {displayed.growth_rate_reasoning && (
              <p className="text-[10px] text-gray-500 mt-2 pt-2 border-t border-border/40">
                <span className="text-gray-400 font-medium">Why {displayed.growth_rate_pct}%, not the raw historical rate: </span>
                {displayed.growth_rate_reasoning}
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <ThesisQaCard label="What is the demand?" text={displayed.demand} accent="#3b82f6" />
            <ThesisQaCard label="What is the moat?" text={displayed.moat} accent="#a78bfa" />
            <div className="bg-card border border-border rounded-xl p-4" style={{ borderLeftColor: '#f59e0b', borderLeftWidth: 2 }}>
              <h4 className="text-xs font-semibold text-gray-300 mb-1.5">
                Is the moat widening or narrowing? <span className={`font-bold ${MOAT_TREND_COLOR[displayed.moat_trend] ?? 'text-gray-400'}`}>{displayed.moat_trend}</span>
              </h4>
              <p className="text-sm text-gray-400 leading-relaxed">{displayed.moat_trend_reason}</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4" style={{ borderLeftColor: displayed.numbers_support_story ? '#34d399' : '#f87171', borderLeftWidth: 2 }}>
              <h4 className="text-xs font-semibold text-gray-300 mb-1.5">
                Do the numbers complete the story? <span className={displayed.numbers_support_story ? 'text-emerald-400 font-bold' : 'text-red-400 font-bold'}>{displayed.numbers_support_story ? 'Yes' : 'No'}</span>
              </h4>
              <p className="text-sm text-gray-400 leading-relaxed">{displayed.numbers_support_reason}</p>
            </div>
          </div>

          {displayed.main_risks?.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-4" style={{ borderTopColor: '#f87171', borderTopWidth: 2 }}>
              <h3 className="text-xs font-semibold text-gray-300 mb-2">Main Risks</h3>
              <ul className="space-y-2">
                {displayed.main_risks.map((r: any, i: number) => (
                  <li key={i} className="text-sm">
                    <span className="text-red-400 font-medium">{r.title}</span>
                    <span className="text-gray-400"> — {r.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {displayed.catalysts?.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-4" style={{ borderTopColor: '#38bdf8', borderTopWidth: 2 }}>
              <h3 className="text-xs font-semibold text-gray-300 mb-2">Catalysts / Events</h3>
              <ul className="space-y-2">
                {displayed.catalysts.map((c: any, i: number) => (
                  <li key={i} className="text-sm">
                    <span className="text-sky-400 font-medium">{c.title}</span>
                    {c.timing && <span className="text-[10px] text-gray-600 ml-2">{c.timing}</span>}
                    <div className="text-gray-400">{c.detail}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {displayed.sources_used?.length > 0 && (
            <div className="text-[10px] text-gray-600">Additional sources: {displayed.sources_used.join(', ')}</div>
          )}
        </div>
      )}

      {history.length > 1 && (
        <div>
          <h2 className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">History</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden divide-y divide-border/50">
            {history.map((h) => (
              <button
                key={h.id}
                onClick={() => loadSnapshot(h.id)}
                className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-white/5 transition-colors text-left"
              >
                <span className="text-xs text-gray-400">{new Date(h.generated_at).toLocaleString()}</span>
                <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded ${STAGE_BADGE_COLOR[h.stage] ?? 'text-gray-400 bg-gray-400/10'}`}>{h.stage}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <button onClick={onBack} className="px-4 py-2 rounded-lg text-sm font-medium bg-white/5 text-gray-400 hover:bg-white/10 transition-colors">
          ← Back to Quality Screen
        </button>
        <button
          onClick={onSkipToDcf}
          disabled={!qa}
          title={!qa ? 'Generate a thesis first' : undefined}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-blue-600/20"
        >
          Continue to DCF →
        </button>
      </div>
    </div>
  )
}

// ── DCF stage (existing scenario builder) ───────────────────────────────────

type Driver = 'fcf' | 'revenue' | 'net_income'
const DRIVER_FIELD: Record<Driver, string> = { fcf: 'free_cashflow', revenue: 'revenue_ttm', net_income: 'net_income_ttm' }
const DRIVER_LABEL: Record<Driver, string> = { fcf: 'Free Cash Flow', revenue: 'Revenue', net_income: 'Net Income' }

interface Scenario {
  stage1_growth: number
  stage1_decay: number
  stage1_years: number
  stage2_growth: number
  stage2_years: number
  terminal_growth: number
  terminal_method: 'gordon' | 'exit_multiple'
  exit_multiple: number | null
  discount_rate: number
}

function defaultScenarios(f: any, driver: Driver): { bear: Scenario; base: Scenario; bull: Scenario } {
  const baseGrowth = f?.revenue_growth_yoy ?? 0.10
  const isRevenue = driver === 'revenue'
  const defaultMultiple = f?.peer_benchmark?.median_ps ?? 5
  // Terminal growth must stay well below the discount rate for Gordon growth
  // to be valid — always leave at least a 2pp spread.
  const safeTerminal = (wanted: number, discountRate: number) => Math.min(Math.max(wanted, 0.01), discountRate - 0.02)
  const mk = (growth: number, discountRate: number, terminalGrowth: number, multiple: number): Scenario => ({
    stage1_growth: growth, stage1_decay: 0.02, stage1_years: 5, stage2_growth: 0, stage2_years: 0,
    terminal_growth: safeTerminal(terminalGrowth, discountRate),
    terminal_method: isRevenue ? 'exit_multiple' : 'gordon',
    exit_multiple: isRevenue ? Math.max(multiple, 1) : null,
    discount_rate: discountRate,
  })
  return {
    bear: mk(Math.max(baseGrowth - 0.10, -0.05), 0.11, 0.02, defaultMultiple - 3),
    base: mk(baseGrowth, 0.09, 0.025, defaultMultiple),
    bull: mk(baseGrowth + 0.10, 0.08, 0.03, defaultMultiple + 3),
  }
}

// The Thesis's growth call is about one specific metric (growth_basis:
// FCF/Sales/Earnings). FCF growth, revenue growth, and net income growth are
// frequently different numbers for the same company (operating leverage,
// heavy reinvestment, etc.) — so only apply the Thesis's rate when it
// actually matches the selected driver; otherwise fall back to that driver's
// own historical growth.
const GROWTH_BASIS_TO_DRIVER: Record<string, Driver> = { FCF: 'fcf', Sales: 'revenue', Earnings: 'net_income' }

// Each driver's own historical CAGR — a real, driver-specific growth signal
// now that fundamentals fetches FCF/revenue/net income history independently
// (previously FCF had no history of its own and fell back to revenue growth).
function driverGrowthFallback(f: any, driver: Driver): number {
  const cagr = driver === 'revenue' ? f?.revenue_cagr : driver === 'net_income' ? f?.net_income_cagr : f?.fcf_cagr
  return Math.min(Math.max(cagr ?? f?.revenue_growth_yoy ?? 0.10, -0.05), 0.60)
}

// Stage 1 = the Thesis's headline growth call, when it's about the selected
// driver's metric (see above) — otherwise the driver's own historical
// growth. The Thesis's "normalized" growth is a business concept — for a
// strong long-term compounder it can legitimately be well above a perpetuity
// rate — so it feeds a realistic Stage 2 follow-on window, not the DCF's
// terminal rate directly. Terminal growth is always kept conservative and
// safely below the discount rate, which Gordon growth requires
// mathematically. Bear/bull are offsets from the base case. exit_multiple is
// always populated (even in Gordon mode) with the multiple Gordon itself
// implies, so switching methods — or the Method Agreement check — starts
// from a self-consistent number rather than an arbitrary default.
function defaultScenariosFromThesis(thesis: any, f: any, driver: Driver): { bear: Scenario; base: Scenario; bull: Scenario } {
  const basisMatches = GROWTH_BASIS_TO_DRIVER[thesis?.growth_basis] === driver
  const fallbackGrowth = driverGrowthFallback(f, driver)
  const stage1Growth = basisMatches ? (thesis?.growth_rate_pct ?? 10) / 100 : fallbackGrowth
  const stage2Growth = basisMatches ? (thesis?.normalized_growth_pct ?? 5) / 100 : Math.max(fallbackGrowth - 0.05, 0.03)
  const stage1Years = basisMatches ? (thesis?.growth_years ?? 5) : 5
  const stage2Years = 5
  const isRevenue = driver === 'revenue'
  const defaultMultiple = f?.peer_benchmark?.median_ps ?? 5

  const mk = (growthDelta: number, discountRate: number, stage2Delta: number, multipleDelta: number): Scenario => {
    const terminalGrowth = Math.min(0.025, discountRate - 0.02)
    const exitMultiple = isRevenue
      ? Math.max(defaultMultiple + multipleDelta, 1)
      : Math.round(((impliedMultipleFromGordon(terminalGrowth, discountRate) ?? 15) + multipleDelta) * 100) / 100
    return {
      stage1_growth: Math.max(stage1Growth + growthDelta, -0.05),
      stage1_decay: 0,
      stage1_years: stage1Years,
      stage2_growth: Math.max(stage2Growth + stage2Delta, terminalGrowth + 0.005),
      stage2_years: stage2Years,
      terminal_growth: terminalGrowth,
      terminal_method: isRevenue ? 'exit_multiple' : 'gordon',
      exit_multiple: Math.max(exitMultiple, 1),
      discount_rate: discountRate,
    }
  }

  return {
    bear: mk(-0.15, 0.11, -0.02, -3),
    base: mk(0, 0.09, 0, 0),
    bull: mk(0.15, 0.08, 0.02, 3),
  }
}

function ScenarioForm({ label, color, value, onChange }: {
  label: string; color: string; value: Scenario; onChange: (s: Scenario) => void
}) {
  // Percent fields are stored as decimals (0.15) but edited as percentages (15).
  // Whichever terminal field is hidden (exit_multiple in Gordon mode, or vice
  // versa) is kept self-consistent with the visible one, so the Method
  // Agreement check always compares against a number the user actually
  // implied — not a stale/arbitrary default.
  const pct = (key: 'stage1_growth' | 'stage1_decay' | 'stage2_growth' | 'terminal_growth' | 'discount_rate', fieldLabel: string, step = 0.5) => (
    <label className="block">
      <span className="text-[10px] text-gray-600">{fieldLabel}</span>
      <div className="relative mt-0.5">
        <input
          type="number"
          step={step}
          value={Math.round(value[key] * 1000) / 10}
          onChange={(e) => {
            const next = { ...value, [key]: (parseFloat(e.target.value) || 0) / 100 }
            if (value.terminal_method === 'gordon' && (key === 'terminal_growth' || key === 'discount_rate')) {
              const m = impliedMultipleFromGordon(next.terminal_growth, next.discount_rate)
              if (m != null) next.exit_multiple = Math.round(m * 100) / 100
            } else if (value.terminal_method === 'exit_multiple' && key === 'discount_rate' && next.exit_multiple) {
              const g = impliedGrowthFromMultiple(next.exit_multiple, next.discount_rate)
              if (g != null) next.terminal_growth = Math.round(g * 10000) / 10000
            }
            onChange(next)
          }}
          className="w-full bg-surface border border-border rounded px-2 py-1 pr-5 text-xs text-gray-100 focus:outline-none focus:border-blue-500"
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-gray-600 pointer-events-none">%</span>
      </div>
    </label>
  )
  const int = (key: 'stage1_years' | 'stage2_years', fieldLabel: string) => (
    <label className="block">
      <span className="text-[10px] text-gray-600">{fieldLabel}</span>
      <input
        type="number" min={0} step={1}
        value={value[key]}
        onChange={(e) => onChange({ ...value, [key]: parseInt(e.target.value) || 0 })}
        className="w-full bg-surface border border-border rounded px-2 py-1 text-xs text-gray-100 mt-0.5 focus:outline-none focus:border-blue-500"
      />
    </label>
  )
  const multiple = () => (
    <label className="block">
      <span className="text-[10px] text-gray-600">Exit multiple</span>
      <div className="relative mt-0.5">
        <input
          type="number" step={0.5} min={0}
          value={value.exit_multiple ?? 0}
          onChange={(e) => {
            const next = { ...value, exit_multiple: parseFloat(e.target.value) || 0 }
            if (value.terminal_method === 'exit_multiple' && next.exit_multiple) {
              const g = impliedGrowthFromMultiple(next.exit_multiple, next.discount_rate)
              if (g != null) next.terminal_growth = Math.round(g * 10000) / 10000
            }
            onChange(next)
          }}
          className="w-full bg-surface border border-border rounded px-2 py-1 pr-5 text-xs text-gray-100 focus:outline-none focus:border-blue-500"
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-gray-600 pointer-events-none">x</span>
      </div>
    </label>
  )

  const group = (title: string, children: React.ReactNode, first = false) => (
    <div className={first ? '' : 'mt-2.5 pt-2.5 border-t border-border/40'}>
      <div className="text-[9px] text-gray-600 uppercase tracking-wider mb-1">{title}</div>
      {children}
    </div>
  )

  return (
    <div className="bg-card border border-border rounded-xl p-3" style={{ borderTopColor: color, borderTopWidth: 2 }}>
      <div className={`text-xs font-semibold mb-2 ${color === '#f87171' ? 'text-red-400' : color === '#34d399' ? 'text-emerald-400' : 'text-gray-300'}`}>{label}</div>

      {group('Stage 1', (
        <div className="grid grid-cols-2 gap-2">
          {pct('stage1_growth', 'Growth')}
          {int('stage1_years', 'Years')}
          {pct('stage1_decay', 'Decay (pp/yr)')}
        </div>
      ), true)}

      {group('Stage 2', (
        <div className={value.stage2_years > 0 ? 'grid grid-cols-2 gap-2' : undefined}>
          {int('stage2_years', 'Years (0 = skip)')}
          {value.stage2_years > 0 && pct('stage2_growth', 'Growth')}
        </div>
      ))}

      {group('Terminal Value', value.terminal_method === 'gordon' ? pct('terminal_growth', 'Terminal growth') : multiple())}

      {group('Discount Rate', pct('discount_rate', 'Discount rate'))}
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
          {sens.discount_rate_axis.map((r: number, ri: number) => (
            <tr key={ri}>
              <td className="px-2 py-1 text-gray-500 whitespace-nowrap">Discount {fmtPct(r)}</td>
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

function DriverPill({ label, active, recommended, onClick }: { label: string; active: boolean; recommended?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={recommended ? 'Recommended for this company' : undefined}
      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${active ? 'bg-blue-600/20 text-blue-400' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'}`}
    >
      {label}
      {recommended && <span className="ml-1 text-emerald-400">★</span>}
    </button>
  )
}

function TerminalCrossCheck({ result }: { result: any }) {
  if (!result) return null
  const usingGordon = result.terminal_method_used === 'gordon'
  const pctTerminal = result.pv_explicit + result.pv_terminal > 0 ? result.pv_terminal / (result.pv_explicit + result.pv_terminal) : null
  return (
    <div className="text-[10px] text-gray-600">
      <div>
        {usingGordon
          ? `Gordon growth used — implies a ${result.implied_exit_multiple_from_gordon ?? '—'}x exit multiple`
          : `${result.assumptions.exit_multiple}x exit multiple used — implies ${fmtPct(result.implied_perpetuity_growth_from_exit_multiple)} perpetuity growth`}
      </div>
      {pctTerminal != null && <div>{fmtPct(pctTerminal)} of value is in the terminal value</div>}
    </div>
  )
}

// Compares the headline implied price against what the OTHER terminal
// method would produce with self-consistent assumptions (see ScenarioForm's
// sync logic) — a check that the growth story and the market-multiple story
// roughly agree, not a second opinion on the business itself.
function MethodAgreement({
  startingValue, shares, netDebt, includeBridge, dilutionRate, dilutionYears, base,
}: {
  startingValue: number; shares: number; netDebt: number; includeBridge: boolean
  dilutionRate: number; dilutionYears: number; base: any
}) {
  if (!base?.assumptions) return null
  const flipped = { ...base.assumptions, terminal_method: base.terminal_method_used === 'gordon' ? 'exit_multiple' : 'gordon' }
  const alt = runScenario(startingValue, shares, netDebt, includeBridge, dilutionRate, dilutionYears, flipped)
  if (alt.error || base.implied_price == null || alt.implied_price == null) return null

  const gordonPrice = base.terminal_method_used === 'gordon' ? base.implied_price : alt.implied_price
  const exitPrice = base.terminal_method_used === 'gordon' ? alt.implied_price : base.implied_price
  const diff = Math.abs(gordonPrice - exitPrice) / Math.max(gordonPrice, exitPrice)
  const verdict = diff < 0.10
    ? { label: 'Methods agree — valuation looks robust', color: 'text-emerald-400' }
    : diff < 0.25
      ? { label: 'Some divergence — worth reviewing assumptions', color: 'text-yellow-400' }
      : { label: 'Methods diverge significantly — assumptions may be inconsistent', color: 'text-red-400' }

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <h3 className="text-xs font-semibold text-gray-300 mb-2">Method Agreement (Base Case)</h3>
      <div className="grid grid-cols-2 gap-3 mb-2">
        <Stat label="Perpetuity Method" value={fmtUsd(gordonPrice)} />
        <Stat label="Exit Multiple Method" value={fmtUsd(exitPrice)} />
      </div>
      <p className={`text-xs font-medium ${verdict.color}`}>{verdict.label} ({fmtPct(diff)} apart)</p>
    </div>
  )
}

function ProjectionTable({ result, driverLabel }: { result: any; driverLabel: string }) {
  if (!result?.projection?.length) return null
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-[9px] text-gray-600 uppercase tracking-wider">
            <th className="text-left font-normal py-1 px-1">Year</th>
            <th className="text-right font-normal py-1 px-1">Growth</th>
            <th className="text-right font-normal py-1 px-1">{driverLabel}</th>
            <th className="text-right font-normal py-1 px-1">Discount Factor</th>
            <th className="text-right font-normal py-1 px-1">PV</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          {result.projection.map((row: any) => (
            <tr key={row.year}>
              <td className="py-1 px-1 text-gray-300">{row.year}</td>
              <td className="py-1 px-1 text-right text-gray-400 tabular-nums">{fmtPct(row.growth)}</td>
              <td className="py-1 px-1 text-right text-gray-300 tabular-nums">{fmtBig(row.value)}</td>
              <td className="py-1 px-1 text-right text-gray-500 tabular-nums">{(row.pv / row.value).toFixed(4)}</td>
              <td className="py-1 px-1 text-right text-gray-300 tabular-nums">{fmtBig(row.pv)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// The gate between Thesis and DCF: which driver actually fits this company,
// decided mechanically from data already fetched — no AI, no network call.
// Financials get Net Income (FCF/capex isn't a meaningful driver there);
// real positive FCF gets the direct, standard FCF approach; negative/absent
// FCF with real growth gets Revenue (a perpetuity off negative cash flow
// isn't coherent); anything else falls back to Revenue with a caveat.
function recommendDriver(f: any): { driver: Driver; reason: string } {
  const sectorIndustry = `${f?.sector ?? ''} ${f?.industry ?? ''}`.toLowerCase()
  const isFinancial = ['bank', 'insurance', 'capital markets', 'asset management', 'financial services'].some((k) => sectorIndustry.includes(k))
  if (isFinancial) {
    return { driver: 'net_income', reason: `${f?.industry ?? f?.sector ?? 'This sector'}: FCF/capex isn't a meaningful valuation driver — net income is standard.` }
  }

  const fcf = f?.free_cashflow
  if (fcf != null && fcf > 0) {
    return { driver: 'fcf', reason: `Free cash flow is positive (${fmtBig(fcf)} TTM) — the most direct, standard approach.` }
  }

  const revGrowth = f?.revenue_growth_yoy
  if (revGrowth != null && revGrowth > 0.15) {
    return { driver: 'revenue', reason: `FCF is negative or unavailable, but revenue is growing ${fmtPct(revGrowth)} YoY — a revenue-multiple approach avoids modeling a perpetuity off negative cash flow.` }
  }

  return { driver: 'revenue', reason: 'FCF is negative or unavailable and growth is modest — revenue is the most stable available base, though this case deserves extra scrutiny.' }
}

function DcfStage({ ticker, fundamentals, thesis, onBack }: { ticker: string; fundamentals: any; thesis: any; onBack: () => void }) {
  const recommended = useMemo(() => recommendDriver(fundamentals), [fundamentals])
  const thesisDriver = thesis ? GROWTH_BASIS_TO_DRIVER[thesis.growth_basis] : undefined
  const [driver, setDriver] = useState<Driver>(() => recommended.driver)
  const [terminalMethod, setTerminalMethod] = useState<'gordon' | 'exit_multiple'>('gordon')
  const [includeBridge, setIncludeBridge] = useState(true)
  const [dilutionRate, setDilutionRate] = useState(0)  // %, e.g. 2 for 2%/yr
  const [dilutionYears, setDilutionYears] = useState(0)

  const buildDefaults = (d: Driver) => (thesis ? defaultScenariosFromThesis(thesis, fundamentals, d) : defaultScenarios(fundamentals, d))
  const [scenarios, setScenarios] = useState<{ bear: Scenario; base: Scenario; bull: Scenario }>(() => buildDefaults(recommended.driver))

  const [history, setHistory] = useState<any[]>([])
  const [viewingRun, setViewingRun] = useState<any>(null)
  const [savedThesis, setSavedThesis] = useState<any>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    api.thesis.history(ticker).then(setHistory).catch(() => setHistory([]))
  }, [ticker])

  function changeDriver(d: Driver) {
    setDriver(d)
    setTerminalMethod(d === 'revenue' ? 'exit_multiple' : 'gordon')
    setIncludeBridge(d !== 'net_income')
    setScenarios(buildDefaults(d))
  }

  function changeTerminalMethod(method: 'gordon' | 'exit_multiple') {
    setTerminalMethod(method)
    setScenarios((prev) => {
      const apply = (s: Scenario): Scenario => ({ ...s, terminal_method: method, exit_multiple: method === 'exit_multiple' ? (s.exit_multiple ?? 15) : s.exit_multiple })
      return { bear: apply(prev.bear), base: apply(prev.base), bull: apply(prev.bull) }
    })
  }

  const startingValue = fundamentals?.[DRIVER_FIELD[driver]]
  const shares = fundamentals?.shares_outstanding
  const netDebt = fundamentals?.net_debt ?? 0

  // Pure local arithmetic — recomputes on every keystroke, no network call.
  const liveResult = useMemo(() => {
    if (startingValue == null || !shares) return null
    return runDcf(driver, startingValue, shares, netDebt, includeBridge, dilutionRate / 100, dilutionYears, scenarios.bear, scenarios.base, scenarios.bull)
  }, [driver, startingValue, shares, netDebt, includeBridge, dilutionRate, dilutionYears, scenarios])

  const hasError = liveResult && (liveResult.bear.error || liveResult.base.error || liveResult.bull.error)

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    try {
      const run = await api.thesis.generate(ticker, {
        driver,
        include_net_debt_bridge: includeBridge,
        dilution_rate: dilutionRate / 100,
        dilution_years: dilutionYears,
        bear: scenarios.bear, base: scenarios.base, bull: scenarios.bull,
      })
      setSavedThesis({
        thesis_text: run.thesis_text,
        risks_json: run.risks_json,
        scenario_commentary: run.dcf_outputs_json?.scenario_commentary,
        target_price: run.target_price,
        created_at: run.created_at,
      })
      setViewingRun(null)
      api.thesis.history(ticker).then(setHistory).catch(() => {})
    } catch (e: any) {
      setSaveError(String(e.message || e))
    } finally {
      setSaving(false)
    }
  }

  async function loadRun(id: number) {
    const run = await api.thesis.run(id)
    setViewingRun(run)
  }

  // Normalize live vs. historical into one shape so the results section below
  // renders identically either way.
  const displayed = viewingRun
    ? {
        current_price: viewingRun.current_price,
        bear: viewingRun.dcf_outputs_json.bear, base: viewingRun.dcf_outputs_json.base, bull: viewingRun.dcf_outputs_json.bull,
        sensitivity: viewingRun.dcf_outputs_json.sensitivity,
        thesis_text: viewingRun.thesis_text, risks_json: viewingRun.risks_json,
        scenario_commentary: viewingRun.dcf_outputs_json.scenario_commentary,
        target_price: viewingRun.target_price, writtenAt: viewingRun.created_at,
      }
    : liveResult
      ? {
          current_price: fundamentals?.current_price,
          bear: liveResult.bear, base: liveResult.base, bull: liveResult.bull, sensitivity: liveResult.sensitivity,
          thesis_text: savedThesis?.thesis_text, risks_json: savedThesis?.risks_json,
          scenario_commentary: savedThesis?.scenario_commentary,
          target_price: savedThesis?.target_price, writtenAt: savedThesis?.created_at,
        }
      : null

  // For a historical run, recover the exact inputs that produced it (from
  // the fundamentals snapshot + request stored alongside) rather than
  // reusing today's live inputs — a past run's numbers were computed against
  // whatever fundamentals existed at that time.
  const methodCheckInputs = viewingRun
    ? {
        driverLabel: DRIVER_LABEL[viewingRun.dcf_outputs_json.driver as Driver],
        startingValue: viewingRun.fundamentals_json?.[DRIVER_FIELD[viewingRun.dcf_outputs_json.driver as Driver]],
        shares: viewingRun.fundamentals_json?.shares_outstanding,
        netDebt: viewingRun.fundamentals_json?.net_debt ?? 0,
        includeBridge: displayed?.base?.net_debt_bridge_applied ?? true,
        dilutionRate: viewingRun.dcf_inputs_json?.dilution_rate ?? 0,
        dilutionYears: viewingRun.dcf_inputs_json?.dilution_years ?? 0,
      }
    : {
        driverLabel: DRIVER_LABEL[driver],
        startingValue, shares, netDebt, includeBridge,
        dilutionRate: dilutionRate / 100, dilutionYears,
      }

  return (
    <div className="space-y-6">
      <button onClick={onBack} className="text-xs text-blue-400 hover:underline">← Back to Thesis</button>

      <div className="bg-blue-950/20 border border-blue-900/50 rounded-lg px-3 py-2 text-[10px] text-blue-300">
        Recommended model: <strong className="text-blue-200">{DRIVER_LABEL[recommended.driver]}</strong> — {recommended.reason}
        {driver !== recommended.driver && <span className="text-gray-500"> (currently viewing {DRIVER_LABEL[driver]})</span>}
      </div>

      {thesis && thesisDriver && thesisDriver !== driver && (
        <div className="bg-yellow-950/20 border border-yellow-900/50 rounded-lg px-3 py-2 text-[10px] text-yellow-500">
          Heads up — the Thesis's growth call was about <strong>{thesis.growth_basis}</strong> ({thesis.growth_rate_pct}%),
          but you're viewing the <strong>{DRIVER_LABEL[driver]}</strong> driver. Stage 1 growth below defaults to{' '}
          {DRIVER_LABEL[driver]}'s own historical CAGR instead of the Thesis's number — switch to{' '}
          <button onClick={() => changeDriver(thesisDriver)} className="underline hover:text-yellow-300">the {DRIVER_LABEL[thesisDriver]} driver</button>{' '}
          to use the Thesis's {thesis.growth_rate_pct}% call directly, or edit Stage 1 growth manually below.
        </div>
      )}

      {thesis && (
        <div className="bg-card border border-border rounded-lg px-3 py-2 text-[10px] text-gray-500">
          Base case prefilled from the Thesis: <span className="text-gray-300">{thesis.stage}</span> stage,{' '}
          <span className="text-gray-300">{thesis.growth_rate_pct}% {thesis.growth_basis?.toLowerCase()}</span> growth for{' '}
          <span className="text-gray-300">{thesis.growth_years} years</span>, normalizing to{' '}
          <span className="text-gray-300">{thesis.normalized_growth_pct}%</span>. Applied to whichever driver is selected below — edit freely.
        </div>
      )}

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex gap-1.5">
            <DriverPill label="FCF" active={driver === 'fcf'} recommended={recommended.driver === 'fcf'} onClick={() => changeDriver('fcf')} />
            <DriverPill label="Revenue" active={driver === 'revenue'} recommended={recommended.driver === 'revenue'} onClick={() => changeDriver('revenue')} />
            <DriverPill label="Net Income" active={driver === 'net_income'} recommended={recommended.driver === 'net_income'} onClick={() => changeDriver('net_income')} />
          </div>
          <div className="text-[10px] text-gray-600">
            Starting {DRIVER_LABEL[driver]}: <span className="text-gray-300">{startingValue != null ? fmtBig(startingValue) : 'not available — enter manually'}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-[10px] text-gray-600">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={includeBridge} disabled={driver === 'net_income'} onChange={(e) => setIncludeBridge(e.target.checked)} />
            Net debt bridge {driver === 'net_income' && '(n/a — net income is already equity-level)'}
          </label>
          <div className="flex items-center gap-1.5">
            <span>Terminal method:</span>
            <button onClick={() => changeTerminalMethod('gordon')} disabled={driver === 'revenue'} className={`px-2 py-0.5 rounded ${terminalMethod === 'gordon' ? 'bg-blue-600/20 text-blue-400' : 'text-gray-500 hover:text-gray-300'} disabled:opacity-30`}>Gordon growth</button>
            <button onClick={() => changeTerminalMethod('exit_multiple')} className={`px-2 py-0.5 rounded ${terminalMethod === 'exit_multiple' ? 'bg-blue-600/20 text-blue-400' : 'text-gray-500 hover:text-gray-300'}`}>Exit multiple</button>
          </div>
          <label className="flex items-center gap-1.5">
            Dilution
            <input type="number" step={0.5} value={dilutionRate} onChange={(e) => setDilutionRate(parseFloat(e.target.value) || 0)} className="w-14 bg-surface border border-border rounded px-1.5 py-0.5 text-gray-100" />
            % / yr for
            <input type="number" step={1} min={0} value={dilutionYears} onChange={(e) => setDilutionYears(parseInt(e.target.value) || 0)} className="w-12 bg-surface border border-border rounded px-1.5 py-0.5 text-gray-100" />
            years
          </label>
        </div>
      </div>

      <div>
        <h2 className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">DCF Assumptions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <ScenarioForm label="Bear" color="#f87171" value={scenarios.bear} onChange={(s) => setScenarios({ ...scenarios, bear: s })} />
          <ScenarioForm label="Base" color="#9ca3af" value={scenarios.base} onChange={(s) => setScenarios({ ...scenarios, base: s })} />
          <ScenarioForm label="Bull" color="#34d399" value={scenarios.bull} onChange={(s) => setScenarios({ ...scenarios, bull: s })} />
        </div>
      </div>

      {!liveResult && !viewingRun && (
        <p className="text-xs text-gray-600">Missing {DRIVER_LABEL[driver].toLowerCase()} or shares outstanding for {ticker} — can't calculate.</p>
      )}

      {displayed && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-[10px] text-gray-600 uppercase tracking-wider">
              {viewingRun ? `Saved run · ${new Date(viewingRun.created_at).toLocaleString()}` : 'Live — updates as you edit assumptions'}
            </h2>
            {viewingRun && (
              <button onClick={() => setViewingRun(null)} className="text-[10px] text-blue-400 hover:underline">Back to current</button>
            )}
          </div>

          {!viewingRun && (liveResult?.bear.error || liveResult?.base.error || liveResult?.bull.error) && (
            <div className="text-xs text-red-400 space-y-0.5">
              {liveResult.bear.error && <p>Bear: {liveResult.bear.error}</p>}
              {liveResult.base.error && <p>Base: {liveResult.base.error}</p>}
              {liveResult.bull.error && <p>Bull: {liveResult.bull.error}</p>}
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Stat label="Bear FV" value={fmtUsd(displayed.bear.implied_price)} color={upsideColor(displayed.current_price, displayed.bear.implied_price)} />
            <Stat label="Base FV" value={fmtUsd(displayed.base.implied_price)} color={upsideColor(displayed.current_price, displayed.base.implied_price)} />
            <Stat label="Bull FV" value={fmtUsd(displayed.bull.implied_price)} color={upsideColor(displayed.current_price, displayed.bull.implied_price)} />
            <Stat label="Target Price" value={fmtUsd(displayed.target_price)} color={upsideColor(displayed.current_price, displayed.target_price)} bold />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-center">
            <TerminalCrossCheck result={displayed.bear} />
            <TerminalCrossCheck result={displayed.base} />
            <TerminalCrossCheck result={displayed.bull} />
          </div>

          {displayed.base?.diluted_shares && fundamentals?.shares_outstanding && (
            <div className="text-[10px] text-gray-600 text-center">
              Diluted shares at horizon: {(displayed.base.diluted_shares / 1e6).toFixed(0)}M (from {(fundamentals.shares_outstanding / 1e6).toFixed(0)}M today)
            </div>
          )}

          {methodCheckInputs.startingValue != null && methodCheckInputs.shares != null && (
            <MethodAgreement
              startingValue={methodCheckInputs.startingValue}
              shares={methodCheckInputs.shares}
              netDebt={methodCheckInputs.netDebt}
              includeBridge={methodCheckInputs.includeBridge}
              dilutionRate={methodCheckInputs.dilutionRate}
              dilutionYears={methodCheckInputs.dilutionYears}
              base={displayed.base}
            />
          )}

          <div className="bg-card border border-border rounded-xl p-4">
            <h3 className="text-xs font-semibold text-gray-300 mb-2">
              Year-by-Year Projection (Base Case) — {methodCheckInputs.driverLabel}
            </h3>
            <ProjectionTable result={displayed.base} driverLabel={methodCheckInputs.driverLabel} />
          </div>

          {!viewingRun && (
            <div className="flex items-center gap-3">
              <button
                onClick={handleSave}
                disabled={saving || !!hasError}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors disabled:opacity-40"
              >
                {saving ? 'Saving…' : 'Save & Write Thesis'}
              </button>
              <span className="text-[10px] text-gray-600">Persists this run to history and writes the narrative, risks, and target price below.</span>
            </div>
          )}
          {saveError && <p className="text-xs text-red-400">{saveError}</p>}

          {displayed.thesis_text ? (
            <>
              {displayed.writtenAt && (
                <p className="text-[10px] text-gray-600">Written {new Date(displayed.writtenAt).toLocaleString()} — based on the inputs at that time.</p>
              )}
              <div className="bg-card border border-border rounded-xl p-4">
                <h3 className="text-xs font-semibold text-gray-300 mb-1.5">Thesis</h3>
                <p className="text-sm text-gray-300 leading-relaxed">{displayed.thesis_text}</p>
              </div>

              {displayed.scenario_commentary && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <CommentaryCard label="Bear" text={displayed.scenario_commentary.bear} color="text-red-400" />
                  <CommentaryCard label="Base" text={displayed.scenario_commentary.base} color="text-gray-300" />
                  <CommentaryCard label="Bull" text={displayed.scenario_commentary.bull} color="text-emerald-400" />
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
            </>
          ) : !viewingRun && (
            <p className="text-xs text-gray-600">No written thesis yet for these numbers — hit Save & Write Thesis above.</p>
          )}

          {displayed.sensitivity && (
            <div className="bg-card border border-border rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-300 mb-2">Sensitivity — Implied Price (Base Case, Gordon Growth)</h3>
              <SensitivityTable sens={displayed.sensitivity} current={displayed.current_price} />
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
  const [refreshing, setRefreshing] = useState(false)
  const [fundamentalsHistory, setFundamentalsHistory] = useState<any[]>([])
  const [viewingFundamentals, setViewingFundamentals] = useState<any>(null)
  const [thesisQa, setThesisQa] = useState<any>(null)
  const [stage, setStage] = useState<Stage>('quality')
  const [unlocked, setUnlocked] = useState<Stage[]>(['quality'])

  useEffect(() => {
    setLoadingFundamentals(true)
    setViewingFundamentals(null)
    api.thesis.fundamentals(ticker)
      .then((f) => setFundamentals(f))
      .catch((e) => setFundamentalsError(String(e.message || e)))
      .finally(() => setLoadingFundamentals(false))
    api.thesis.fundamentalsHistory(ticker).then(setFundamentalsHistory).catch(() => setFundamentalsHistory([]))
  }, [ticker])

  async function handleRefresh() {
    setRefreshing(true)
    setFundamentalsError(null)
    try {
      const f = await api.thesis.refreshFundamentals(ticker)
      setFundamentals(f)
      setViewingFundamentals(null)
      api.thesis.fundamentalsHistory(ticker).then(setFundamentalsHistory).catch(() => {})
    } catch (e: any) {
      setFundamentalsError(String(e.message || e))
    } finally {
      setRefreshing(false)
    }
  }

  async function loadFundamentalsSnapshot(id: number) {
    const snap = await api.thesis.fundamentalsSnapshot(ticker, id)
    setViewingFundamentals(snap)
  }

  function goTo(s: Stage) {
    if (s === 'dcf' && !thesisQa) return  // DCF stays locked until a thesis exists — it prefills from it
    setUnlocked((prev) => (prev.includes(s) ? prev : [...prev, s]))
    setStage(s)
  }

  const effectiveUnlocked = thesisQa ? unlocked : unlocked.filter((s) => s !== 'dcf')

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
            <div className="text-[10px] text-gray-600 flex items-center gap-1.5 justify-end">
              {fundamentals._cached_at ? `Data as of ${new Date(fundamentals._cached_at).toLocaleString()}` : 'Just fetched'}
              <button onClick={handleRefresh} disabled={refreshing} className="text-blue-400 hover:underline disabled:opacity-40">
                {refreshing ? 'Refreshing…' : 'Refresh Data'}
              </button>
            </div>
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
          <StageStepper stage={stage} unlocked={effectiveUnlocked} onSelect={goTo} />

          {stage === 'quality' && (
            <>
              {viewingFundamentals && (
                <div className="bg-yellow-950/20 border border-yellow-900/50 rounded-lg px-3 py-2 text-xs text-yellow-500 flex items-center justify-between">
                  <span>Viewing historical snapshot from {new Date(viewingFundamentals._cached_at).toLocaleString()}</span>
                  <button onClick={() => setViewingFundamentals(null)} className="text-blue-400 hover:underline">Back to current</button>
                </div>
              )}
              <QualityScreen f={viewingFundamentals ?? fundamentals} onContinue={() => goTo('thesis')} />
              {fundamentalsHistory.length > 1 && (
                <div>
                  <h2 className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">Fundamentals History</h2>
                  <div className="bg-card border border-border rounded-xl overflow-hidden divide-y divide-border/50">
                    {fundamentalsHistory.map((h) => (
                      <button
                        key={h.id}
                        onClick={() => loadFundamentalsSnapshot(h.id)}
                        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-white/5 transition-colors text-left"
                      >
                        <span className="text-xs text-gray-400">{new Date(h.fetched_at).toLocaleString()}</span>
                        <span className="text-xs text-gray-300 tabular-nums">Price {fmtUsd(h.current_price)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
          {stage === 'thesis' && (
            <ThesisStage
              ticker={ticker}
              fundamentals={fundamentals}
              onBack={() => goTo('quality')}
              onSkipToDcf={() => goTo('dcf')}
              onThesisChange={setThesisQa}
            />
          )}
          {stage === 'dcf' && <DcfStage ticker={ticker} fundamentals={fundamentals} thesis={thesisQa} onBack={() => goTo('thesis')} />}
        </>
      )}
    </div>
  )
}
