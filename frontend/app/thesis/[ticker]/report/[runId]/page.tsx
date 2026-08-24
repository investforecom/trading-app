'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'
import { fmtUsd, fmtBig, fmtPct, fmtRatio, vsCurrentPct } from '@/lib/format'

const DRIVER_LABEL: Record<string, string> = { fcf: 'Free Cash Flow', revenue: 'Revenue', net_income: 'Net Income' }

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8 break-inside-avoid">
      <h2 className="text-sm font-semibold text-gray-100 uppercase tracking-wider border-b border-border pb-2 mb-3">{title}</h2>
      {children}
    </section>
  )
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-semibold text-gray-300 mt-4 mb-1.5 first:mt-0">{children}</h3>
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-xs border-b border-border/30">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-200 tabular-nums font-medium text-right">{value}</span>
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

  return (
    <div className="report-print max-w-3xl mx-auto py-8 px-4">
      <style>{`
        @media print {
          body * { visibility: hidden; }
          .report-print, .report-print * { visibility: visible; }
          .report-print { position: absolute; left: 0; top: 0; width: 100%; padding: 0; margin: 0; max-width: none; }
          .no-print { display: none !important; }
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

      <Section title="Quality Screen">
        <SubHeading>Growth (Income Statement)</SubHeading>
        <Row label="Revenue" value={`${fmtBig(f.revenue_ttm)} TTM · ${fmtPct(f.revenue_growth_yoy, true)} YoY · ${fmtPct(f.revenue_cagr, true)} CAGR`} />
        <Row label="Gross Profit" value={`${fmtBig(f.gross_profit_ttm)} TTM · ${fmtPct(f.gross_profit_yoy, true)} YoY · ${fmtPct(f.gross_profit_cagr, true)} CAGR`} />
        <Row label="Operating Income" value={`${fmtBig(f.operating_income_ttm)} TTM · ${fmtPct(f.operating_income_yoy, true)} YoY · ${fmtPct(f.operating_income_cagr, true)} CAGR`} />
        <Row label="Net Income" value={`${fmtBig(f.net_income_ttm)} TTM · ${fmtPct(f.net_income_yoy, true)} YoY · ${fmtPct(f.net_income_cagr, true)} CAGR`} />

        <SubHeading>Cash Conversion</SubHeading>
        <Row label="Operating Cash Flow" value={`${fmtBig(f.operating_cashflow_ttm)} TTM · ${fmtPct(f.operating_cashflow_yoy, true)} YoY · ${fmtPct(f.operating_cashflow_cagr, true)} CAGR`} />
        <Row label="Capex (latest FY)" value={`${fmtBig(f.capex_ttm)} · ${fmtPct(f.capex_yoy, true)} YoY · ${fmtPct(f.capex_cagr, true)} CAGR`} />
        <Row label="Free Cash Flow" value={`${fmtBig(f.free_cashflow)} TTM · ${fmtPct(f.fcf_yoy, true)} YoY · ${fmtPct(f.fcf_cagr, true)} CAGR`} />

        <SubHeading>Profitability</SubHeading>
        <Row label="Gross margin" value={fmtPct(f.gross_margin)} />
        <Row label="Operating margin" value={fmtPct(f.operating_margin)} />
        <Row label="EBITDA margin" value={fmtPct(f.ebitda_margin)} />
        <Row label="Net margin" value={fmtPct(f.profit_margin)} />
        <Row label="Return on equity" value={fmtPct(f.return_on_equity)} />
        <Row label="Return on assets" value={fmtPct(f.return_on_assets)} />

        <SubHeading>Balance Sheet</SubHeading>
        <Row label="Net debt (cash if negative)" value={fmtBig(f.net_debt)} />
        <Row label="Net debt / EBITDA" value={fmtRatio(f.net_debt_to_ebitda)} />
        <Row label="Debt / Equity" value={f.debt_to_equity_pct != null ? `${f.debt_to_equity_pct.toFixed(1)}%` : '—'} />
        <Row label="Current ratio" value={fmtRatio(f.current_ratio)} />
        <Row label="Interest coverage" value={f.interest_coverage != null ? fmtRatio(f.interest_coverage) : '— (negligible debt)'} />

        <SubHeading>Dilution</SubHeading>
        <Row label="Shares outstanding YoY" value={fmtPct(f.shares_yoy, true)} />
        <Row label="Shares CAGR" value={fmtPct(f.shares_cagr, true)} />
        <Row label="Insider ownership" value={fmtPct(f.insider_pct)} />
        <Row label="Institutional ownership" value={fmtPct(f.institution_pct)} />

        <SubHeading>Valuation</SubHeading>
        <Row label="PEG ratio" value={f.peg_ratio != null ? f.peg_ratio.toFixed(2) : '—'} />
        <Row label="Forward P/E" value={fmtRatio(f.forward_pe)} />
        <Row label="Trailing P/E" value={fmtRatio(f.trailing_pe)} />
        <Row label="EV / EBITDA" value={fmtRatio(f.ev_to_ebitda)} />
        <Row label="Price / Sales" value={fmtRatio(f.price_to_sales)} />
        <Row label="Price / Book" value={fmtRatio(f.price_to_book)} />
        <Row label="Analyst target upside" value={fmtPct(analystUpside, true)} />
      </Section>

      {qa && (
        <Section title="Thesis">
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

      <Section title="Top Risks">
        <div className="space-y-2">
          {(run.risks_json ?? []).map((r: any, i: number) => (
            <div key={i} className="text-xs">
              <span className="text-gray-200 font-medium">{i + 1}. {r.title}</span>
              <p className="text-gray-500 mt-0.5">{r.detail}</p>
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}
