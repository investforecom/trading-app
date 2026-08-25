'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'
import { fmtUsd, fmtBig, fmtPct, fmtRatio, vsCurrentPct } from '@/lib/format'
import { type Rating, RATING_TEXT, rateAbove, rateBelow, rateDilution, rateRelative, verdict } from '@/lib/quality'
import { GroupedBarChart } from '@/components/charts/grouped-bar-chart'

const DRIVER_LABEL: Record<string, string> = { fcf: 'Free Cash Flow', revenue: 'Revenue', net_income: 'Net Income' }

function Section({ title, children, avoidBreak = true, pageBreakAfter = false }: { title: string; children: React.ReactNode; avoidBreak?: boolean; pageBreakAfter?: boolean }) {
  return (
    <section className={`mb-8 ${avoidBreak ? 'break-inside-avoid' : ''} ${pageBreakAfter ? 'page-break-after' : ''}`}>
      <h2 className="text-sm font-semibold text-gray-100 uppercase tracking-wider border-b border-border pb-2 mb-3">{title}</h2>
      {children}
    </section>
  )
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-semibold text-gray-300 mt-4 mb-1.5 first:mt-0">{children}</h3>
}

function QualityGroup({ title, accent, verdictInfo, children }: {
  title: string; accent: string; verdictInfo: { label: string; color: string }; children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-border/50 overflow-hidden" style={{ borderTopColor: accent, borderTopWidth: 2 }}>
      <div className="flex items-center justify-between px-2.5 py-1 border-b border-border/40">
        <h3 className="text-[10px] font-semibold text-gray-200">{title}</h3>
        <span className={`text-[9px] font-semibold uppercase tracking-wider ${verdictInfo.color}`}>{verdictInfo.label}</span>
      </div>
      <div className="px-2.5 py-0.5">{children}</div>
    </div>
  )
}

function QLine({ label, value, rating }: { label: string; value: string; rating: Rating }) {
  return (
    <div className="flex items-center justify-between gap-2 py-[2px] text-[9.5px] leading-tight">
      <span className="text-gray-500 truncate">{label}</span>
      <span className={`font-semibold tabular-nums flex-shrink-0 ${RATING_TEXT[rating]}`}>{value}</span>
    </div>
  )
}

const ASSUMPTION_ROWS: [string, (s: any) => string][] = [
  ['Stage 1 growth', (s) => fmtPct(s.stage1_growth)],
  ['Stage 1 length', (s) => `${s.stage1_years}yr`],
  ['Stage 1 decay', (s) => `${fmtPct(s.stage1_decay)}/yr`],
  ['Stage 2 growth', (s) => (s.stage2_years ? fmtPct(s.stage2_growth) : '—')],
  ['Stage 2 length', (s) => (s.stage2_years ? `${s.stage2_years}yr` : 'skipped')],
  ['Terminal value', (s) => (s.terminal_method === 'gordon' ? `${fmtPct(s.terminal_growth)} perpetual growth` : `${s.exit_multiple?.toFixed(1)}x exit multiple`)],
  ['Discount rate', (s) => fmtPct(s.discount_rate)],
]

const SCENARIOS: [string, string][] = [['bear', '#f87171'], ['base', '#9ca3af'], ['bull', '#34d399']]

export default function ThesisReportPage() {
  const params = useParams()
  const ticker = String(params.ticker).toUpperCase()
  const runId = Number(params.runId)

  const [run, setRun] = useState<any>(null)
  const [qa, setQa] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!runId) { setError('No saved run specified.'); setLoading(false); return }
    setLoading(true)
    setError(null)
    Promise.all([api.thesis.run(runId), api.thesis.thesisQa(ticker)])
      .then(([r, q]) => { setRun(r); setQa(q) })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false))
  }, [ticker, runId])

  if (loading) return <div className="text-xs text-gray-600 py-16 text-center">Building report…</div>
  if (error) return <div className="text-xs text-red-400 py-16 text-center">{error}</div>
  if (!run) return null

  const f = run.fundamentals_json ?? {}
  const outputs = run.dcf_outputs_json ?? {}
  const commentary = outputs.scenario_commentary ?? {}
  const driverLabel = DRIVER_LABEL[outputs.driver] ?? outputs.driver
  const analystUpside = f.current_price && f.analyst_target_mean ? f.analyst_target_mean / f.current_price - 1 : null
  const fcfMargin = f.revenue_ttm && f.free_cashflow != null ? f.free_cashflow / f.revenue_ttm : null

  // Same rating thresholds as the interactive Quality Screen — kept in sync via lib/quality.
  const rGrowth = rateAbove(f.revenue_growth_yoy, 0.15, 0)
  const rCagr = rateAbove(f.revenue_cagr, 0.15, 0)
  const rGrossProfitYoy = rateAbove(f.gross_profit_yoy, 0.15, 0)
  const rGrossProfitCagr = rateAbove(f.gross_profit_cagr, 0.15, 0)
  const rOperatingIncomeYoy = rateAbove(f.operating_income_yoy, 0.15, 0)
  const rOperatingIncomeCagr = rateAbove(f.operating_income_cagr, 0.15, 0)
  const rNetIncomeYoy = rateAbove(f.net_income_yoy, 0.15, 0)
  const rNetIncomeCagr = rateAbove(f.net_income_cagr, 0.15, 0)

  const rOcfYoy = rateAbove(f.operating_cashflow_yoy, 0.15, 0)
  const rOcfCagr = rateAbove(f.operating_cashflow_cagr, 0.15, 0)
  const rFcfYoy = rateAbove(f.fcf_yoy, 0.15, 0)
  const rFcfCagr = rateAbove(f.fcf_cagr, 0.15, 0)

  const rGross = rateAbove(f.gross_margin, 0.5, 0.3)
  const rOperating = rateAbove(f.operating_margin, 0.2, 0.1)
  const rEbitda = rateAbove(f.ebitda_margin, 0.25, 0.12)
  const rProfit = rateAbove(f.profit_margin, 0.15, 0.05)
  const rFcf = rateAbove(fcfMargin, 0.15, 0.05)
  const rRoe = rateAbove(f.return_on_equity, 0.20, 0.10)
  const rRoa = rateAbove(f.return_on_assets, 0.10, 0.05)
  const rRoic = rateAbove(f.return_on_invested_capital, 0.12, 0.06)

  const rDebtToEquity = rateBelow(f.debt_to_equity_pct, 40, 100)
  const rCurrentRatio = rateAbove(f.current_ratio, 1.5, 1.0)
  const rNetDebtEbitda = rateBelow(f.net_debt_to_ebitda, 1, 3)
  const rInterestCoverage = f.interest_coverage == null ? 'good' : rateAbove(f.interest_coverage, 8, 3)

  const rDilutionYoy = rateDilution(f.shares_yoy)
  const rDilutionCagr = rateDilution(f.shares_cagr)

  const peer = f.peer_benchmark ?? {}
  const peBenchmark = peer.median_pe ?? f.own_pe_median
  const psBenchmark = peer.median_ps ?? f.own_ps_median
  const pbBenchmark = peer.median_pb ?? f.own_pb_median
  const rPeg = rateBelow(f.peg_ratio, 1, 2)
  const rForwardPe = peer.median_forward_pe != null ? rateRelative(f.forward_pe, peer.median_forward_pe) : rateBelow(f.forward_pe, 20, 35)
  const rTrailingPe = peBenchmark != null ? rateRelative(f.trailing_pe, peBenchmark) : 'na' as Rating
  const rEvEbitda = peer.median_ev_ebitda != null ? rateRelative(f.ev_to_ebitda, peer.median_ev_ebitda) : rateBelow(f.ev_to_ebitda, 15, 25)
  const rPs = psBenchmark != null ? rateRelative(f.price_to_sales, psBenchmark) : rateBelow(f.price_to_sales, 5, 10)
  const rPb = pbBenchmark != null ? rateRelative(f.price_to_book, pbBenchmark) : rateBelow(f.price_to_book, 5, 10)
  const rUpside = rateAbove(analystUpside, 0.15, 0)

  return (
    <div className="report-print max-w-3xl mx-auto py-8 px-4">
      <style>{`
        @media print {
          body * { visibility: hidden; }
          .report-print, .report-print * { visibility: visible; }
          .report-print { position: absolute; left: 0; top: 0; width: 100%; padding: 0; margin: 0; max-width: none; }
          .no-print { display: none !important; }
          .page-break-after { break-after: page; }
          * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; color-adjust: exact !important; }

          /* The app is dark-themed (light text on a near-black body); flip to
             a light page for print so text stays legible on paper. Only the
             hue-carrying colors (chart bars, rating dots/text) are left alone. */
          body { background: #fff !important; }
          .report-print { color: #0f172a !important; }
          .report-print .text-gray-100 { color: #0f172a !important; }
          .report-print .text-gray-200 { color: #1e293b !important; }
          .report-print .text-gray-300 { color: #334155 !important; }
          .report-print .text-gray-400 { color: #475569 !important; }
          .report-print .text-gray-500 { color: #64748b !important; }
          .report-print .text-gray-600 { color: #94a3b8 !important; }
          .report-print .border-border,
          .report-print .border-border\/30,
          .report-print .border-border\/40,
          .report-print .border-border\/50 { border-color: #cbd5e1 !important; }
        }
      `}</style>

      <div className="flex items-center justify-between mb-6 no-print">
        <a href={`/thesis/${ticker}`} className="text-xs text-blue-400 hover:underline">← Back to {ticker}</a>
        <button onClick={() => window.print()} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors">
          Print / Save as PDF
        </button>
      </div>

      <div className="mb-8">
        <h1 className="text-xl font-bold text-gray-100">{ticker} — Investment Report</h1>
        <p className="text-xs text-gray-500 mt-1">
          {f.long_name}{run.name ? ` · ${run.name}` : ''}
        </p>
        <p className="text-[10px] text-gray-600 mt-1">
          Generated {new Date().toLocaleDateString()} · Based on the run saved {new Date(run.created_at).toLocaleString()} at a price of {fmtUsd(run.current_price)}
        </p>
      </div>

      <Section title="Quality Screen" avoidBreak={false} pageBreakAfter>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <QualityGroup title="Reliable growth" accent="#3b82f6"
            verdictInfo={verdict([rGrowth, rCagr, rGrossProfitYoy, rGrossProfitCagr, rOperatingIncomeYoy, rOperatingIncomeCagr, rNetIncomeYoy, rNetIncomeCagr])}>
            <QLine label="Revenue YoY / CAGR" value={`${fmtPct(f.revenue_growth_yoy, true)} / ${fmtPct(f.revenue_cagr, true)}`} rating={rGrowth} />
            <QLine label="Gross profit YoY / CAGR" value={`${fmtPct(f.gross_profit_yoy, true)} / ${fmtPct(f.gross_profit_cagr, true)}`} rating={rGrossProfitYoy} />
            <QLine label="Op. income YoY / CAGR" value={`${fmtPct(f.operating_income_yoy, true)} / ${fmtPct(f.operating_income_cagr, true)}`} rating={rOperatingIncomeYoy} />
            <QLine label="Net income YoY / CAGR" value={`${fmtPct(f.net_income_yoy, true)} / ${fmtPct(f.net_income_cagr, true)}`} rating={rNetIncomeYoy} />
          </QualityGroup>

          <QualityGroup title="Cash conversion" accent="#22d3ee" verdictInfo={verdict([rOcfYoy, rOcfCagr, rFcfYoy, rFcfCagr])}>
            <QLine label="Op. cash flow YoY / CAGR" value={`${fmtPct(f.operating_cashflow_yoy, true)} / ${fmtPct(f.operating_cashflow_cagr, true)}`} rating={rOcfYoy} />
            <QLine label="FCF YoY / CAGR" value={`${fmtPct(f.fcf_yoy, true)} / ${fmtPct(f.fcf_cagr, true)}`} rating={rFcfYoy} />
            <QLine label="Capex (latest FY)" value={fmtBig(f.capex_ttm)} rating="na" />
            <QLine label="Free cash flow (TTM)" value={fmtBig(f.free_cashflow)} rating="na" />
          </QualityGroup>

          <QualityGroup title="Profitability & efficiency" accent="#34d399" verdictInfo={verdict([rGross, rOperating, rEbitda, rProfit, rFcf, rRoe, rRoa, rRoic])}>
            <QLine label="Gross / operating margin" value={`${fmtPct(f.gross_margin)} / ${fmtPct(f.operating_margin)}`} rating={rGross} />
            <QLine label="EBITDA / net margin" value={`${fmtPct(f.ebitda_margin)} / ${fmtPct(f.profit_margin)}`} rating={rEbitda} />
            <QLine label="FCF margin" value={fmtPct(fcfMargin)} rating={rFcf} />
            <QLine label="Return on equity / assets" value={`${fmtPct(f.return_on_equity)} / ${fmtPct(f.return_on_assets)}`} rating={rRoe} />
            <QLine label="Return on invested capital" value={fmtPct(f.return_on_invested_capital)} rating={rRoic} />
          </QualityGroup>

          <QualityGroup title="Balance sheet" accent="#fb923c" verdictInfo={verdict([rDebtToEquity, rCurrentRatio, rNetDebtEbitda, rInterestCoverage])}>
            <QLine label="Net debt (cash if neg.)" value={fmtBig(f.net_debt)} rating="na" />
            <QLine label="Net debt / EBITDA" value={fmtRatio(f.net_debt_to_ebitda)} rating={rNetDebtEbitda} />
            <QLine label="Debt / equity" value={f.debt_to_equity_pct != null ? `${f.debt_to_equity_pct.toFixed(1)}%` : '—'} rating={rDebtToEquity} />
            <QLine label="Current ratio" value={fmtRatio(f.current_ratio)} rating={rCurrentRatio} />
            <QLine label="Interest coverage" value={f.interest_coverage != null ? fmtRatio(f.interest_coverage) : 'negligible debt'} rating={rInterestCoverage} />
          </QualityGroup>

          <QualityGroup title="Dilution" accent="#f59e0b" verdictInfo={verdict([rDilutionYoy, rDilutionCagr])}>
            <QLine label="Shares out. YoY / CAGR" value={`${fmtPct(f.shares_yoy, true)} / ${fmtPct(f.shares_cagr, true)}`} rating={rDilutionYoy} />
            <QLine label="Insider ownership" value={fmtPct(f.insider_pct)} rating="na" />
            <QLine label="Institutional ownership" value={fmtPct(f.institution_pct)} rating="na" />
          </QualityGroup>

          <QualityGroup title="Valuation" accent="#a78bfa" verdictInfo={verdict([rPeg, rForwardPe, rTrailingPe, rEvEbitda, rPs, rPb, rUpside])}>
            <QLine label="PEG / Fwd P/E" value={`${f.peg_ratio != null ? f.peg_ratio.toFixed(2) : '—'} / ${fmtRatio(f.forward_pe)}`} rating={rPeg} />
            <QLine label="Trailing P/E / EV-EBITDA" value={`${fmtRatio(f.trailing_pe)} / ${fmtRatio(f.ev_to_ebitda)}`} rating={rTrailingPe} />
            <QLine label="P/S / P/B" value={`${fmtRatio(f.price_to_sales)} / ${fmtRatio(f.price_to_book)}`} rating={rPs} />
            <QLine label="Analyst target upside" value={fmtPct(analystUpside, true)} rating={rUpside} />
          </QualityGroup>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-border/50 overflow-hidden">
            <div className="px-2.5 py-1 border-b border-border/40">
              <h3 className="text-[10px] font-semibold text-gray-200">Is the business reliable?</h3>
            </div>
            <GroupedBarChart data={f.income_statement_history} series={[
              { key: 'revenue', label: 'Revenue', color: '#60a5fa' },
              { key: 'gross_profit', label: 'Gross Profit', color: '#34d399' },
              { key: 'operating_income', label: 'Op. Income', color: '#fbbf24' },
              { key: 'net_income', label: 'Net Income', color: '#f472b6' },
            ]} />
          </div>
          <div className="rounded-lg border border-border/50 overflow-hidden">
            <div className="px-2.5 py-1 border-b border-border/40">
              <h3 className="text-[10px] font-semibold text-gray-200">Does the business convert profit into cash?</h3>
            </div>
            <GroupedBarChart data={f.cash_flow_history} series={[
              { key: 'operating_cash_flow', label: 'Op. Cash Flow', color: '#60a5fa' },
              { key: 'capex', label: 'Capex', color: '#f87171' },
              { key: 'fcf', label: 'FCF', color: '#34d399' },
            ]} />
          </div>
        </div>
      </Section>

      {qa && (
        <Section title="Business Fundamentals" avoidBreak={false}>
          <SubHeading>Demand</SubHeading>
          <p className="text-xs text-gray-400 leading-relaxed">{qa.demand}</p>

          <SubHeading>Moat — {qa.moat_trend}</SubHeading>
          <p className="text-xs text-gray-400 leading-relaxed">{qa.moat}</p>
          <p className="text-[10px] text-gray-600 mt-1">{qa.moat_trend_reason}</p>

          <SubHeading>Do the numbers support the story? — {qa.numbers_support_story ? 'Yes' : 'No'}</SubHeading>
          <p className="text-xs text-gray-400 leading-relaxed">{qa.numbers_support_reason}</p>

          {qa.growth_rate_reasoning && (
            <>
              <SubHeading>Growth rate rationale</SubHeading>
              <p className="text-xs text-gray-400 leading-relaxed">{qa.growth_rate_reasoning}</p>
            </>
          )}

          {qa.catalysts?.length > 0 && (
            <>
              <SubHeading>Catalysts</SubHeading>
              <div className="space-y-2">
                {qa.catalysts.map((c: any, i: number) => (
                  <div key={i} className="text-xs">
                    <span className="text-gray-200 font-medium">{c.title}</span>
                    <span className="text-gray-600"> — {c.timing}</span>
                    <p className="text-gray-500 mt-0.5">{c.detail}</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </Section>
      )}

      <Section title="Top Risks" pageBreakAfter>
        <div className="space-y-2">
          {(run.risks_json ?? []).map((r: any, i: number) => (
            <div key={i} className="text-xs">
              <span className="text-gray-200 font-medium">{i + 1}. {r.title}</span>
              <p className="text-gray-500 mt-0.5">{r.detail}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title={`DCF — ${driverLabel} Driver`}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-[10px] text-gray-600 uppercase">
                <th className="text-left font-normal py-1">Assumption</th>
                <th className="text-right font-normal py-1">Bear</th>
                <th className="text-right font-normal py-1">Base</th>
                <th className="text-right font-normal py-1">Bull</th>
              </tr>
            </thead>
            <tbody>
              {ASSUMPTION_ROWS.map(([label, fn]) => (
                <tr key={label} className="border-t border-border/30">
                  <td className="py-1 text-gray-500">{label}</td>
                  <td className="py-1 text-right text-gray-300 tabular-nums">{fn(outputs.bear?.assumptions ?? {})}</td>
                  <td className="py-1 text-right text-gray-300 tabular-nums">{fn(outputs.base?.assumptions ?? {})}</td>
                  <td className="py-1 text-right text-gray-300 tabular-nums">{fn(outputs.bull?.assumptions ?? {})}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Adjusted Thesis (DCF-Grounded)">
        <p className="text-xs text-gray-300 leading-relaxed">{run.thesis_text}</p>
      </Section>

      <Section title="Scenarios">
        {SCENARIOS.map(([key, color]) => {
          const res = outputs[key]
          if (!res) return null
          return (
            <div key={key} className="mb-3 pb-3 border-b border-border/30 last:border-0 last:pb-0">
              <div className="flex items-baseline justify-between">
                <span className="text-xs font-semibold capitalize" style={{ color }}>{key}</span>
                <span className="text-xs font-semibold text-gray-200 tabular-nums">
                  {fmtUsd(res.implied_price)}
                  {vsCurrentPct(run.current_price, res.implied_price) && (
                    <span className="text-gray-500 font-normal"> ({vsCurrentPct(run.current_price, res.implied_price)})</span>
                  )}
                </span>
              </div>
              <p className="text-xs text-gray-400 leading-relaxed mt-1">{commentary[key]}</p>
            </div>
          )
        })}
      </Section>
    </div>
  )
}
