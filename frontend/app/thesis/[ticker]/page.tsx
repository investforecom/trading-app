'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'

// ── helpers ───────────────────────────────────────────────────────────────

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
function fmtPct(n: number | null | undefined) {
  if (n == null) return '—'
  return `${(n * 100).toFixed(1)}%`
}
function upsideColor(current: number | null, target: number | null) {
  if (current == null || target == null) return 'text-gray-500'
  return target > current ? 'text-emerald-400' : target < current ? 'text-red-400' : 'text-gray-400'
}

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

// ── Scenario input column ───────────────────────────────────────────────────

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

// ── Sensitivity table ────────────────────────────────────────────────────────

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

// ── Page ──────────────────────────────────────────────────────────────────

export default function ThesisTickerPage() {
  const params = useParams()
  const ticker = String(params.ticker).toUpperCase()

  const [fundamentals, setFundamentals] = useState<any>(null)
  const [fundamentalsError, setFundamentalsError] = useState<string | null>(null)
  const [loadingFundamentals, setLoadingFundamentals] = useState(true)

  const [scenarios, setScenarios] = useState<{ bear: Scenario; base: Scenario; bull: Scenario } | null>(null)
  const [years, setYears] = useState(5)

  const [history, setHistory] = useState<any[]>([])
  const [viewingRun, setViewingRun] = useState<any>(null)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)

  useEffect(() => {
    setLoadingFundamentals(true)
    api.thesis.fetchFundamentals(ticker)
      .then((f) => { setFundamentals(f); setScenarios(defaultScenarios(f)) })
      .catch((e) => setFundamentalsError(String(e.message || e)))
      .finally(() => setLoadingFundamentals(false))
    api.thesis.history(ticker).then(setHistory).catch(() => setHistory([]))
  }, [ticker])

  async function handleGenerate() {
    if (!scenarios) return
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

      {/* Fundamentals */}
      {fundamentals && (
        <div>
          <h2 className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">Fundamentals</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Stat label="Revenue TTM" value={fmtBig(fundamentals.revenue_ttm)} />
            <Stat label="Revenue Growth YoY" value={fmtPct(fundamentals.revenue_growth_yoy)} />
            <Stat label="FCF Margin" value={fundamentals.revenue_ttm ? fmtPct(fundamentals.free_cashflow / fundamentals.revenue_ttm) : '—'} />
            <Stat label="Gross Margin" value={fmtPct(fundamentals.gross_margin)} />
            <Stat label="Market Cap" value={fmtBig(fundamentals.market_cap)} />
            <Stat label="Net Debt" value={fmtBig(fundamentals.net_debt)} />
            <Stat label="Shares Out" value={fundamentals.shares_outstanding ? (fundamentals.shares_outstanding / 1e6).toFixed(0) + 'M' : '—'} />
            <Stat label="Analyst Target (mean)" value={fmtUsd(fundamentals.analyst_target_mean)} />
          </div>
        </div>
      )}

      {/* DCF assumptions */}
      {scenarios && (
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
            disabled={generating || loadingFundamentals}
            className="mt-3 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors disabled:opacity-40"
          >
            {generating ? 'Generating…' : 'Generate Thesis'}
          </button>
          {genError && <p className="text-xs text-red-400 mt-2">{genError}</p>}
        </div>
      )}

      {/* Results */}
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

      {/* History */}
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
