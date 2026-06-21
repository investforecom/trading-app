'use client'

import { useState, useMemo } from 'react'
import Badge from '@/components/ui/badge'

type SortDir = 'asc' | 'desc' | null
type SortKey = 'symbol' | 'underlying' | 'theme' | 'strategy' | 'qty' | 'cost' | 'avg_price' | 'value' | 'gain_pct' | 'pct_nav'

// ── Note normalization ────────────────────────────────────────────────────────

const INLINE_FLAG_RE = [
  /CARDINAL WHEEL VIOLATION/i,
  /\bDOUBLE\s*[—–]/,
  /Thesis check/i,
  /Past SWING HARD STOP/i,
  /\bExit Mon\b/i,
  /[—–]\s*close\s+Mon/i,
  /\bCut on thesis/i,
  /WARNING\s*:/i,
  /High assignment risk/i,
  /WHEEL-STUCK:/i,
]

function splitNote(raw: string | null): { display: string; flag: string | null } {
  if (!raw) return { display: '', flag: null }
  for (const pat of INLINE_FLAG_RE) {
    const m = pat.exec(raw)
    if (m) {
      const clean = raw.slice(0, m.index).trimEnd().replace(/[.\s]+$/, '') + '.'
      return { display: clean, flag: raw.slice(m.index).trim() }
    }
  }
  return { display: raw, flag: null }
}

function parseNote(text: string) {
  return {
    movement: text.match(/((?:Flat|[+-]\d+\.?\d*%)(?:\s*\(was\s+[^)]*\))?)/)?.[1] ?? null,
    duration: text.match(/\b(\d+mo)\b/)?.[1] ?? null,
    structure: text.match(/\b(\d+-wide)\b/)?.[1] ?? null,
    fwdRR:    text.match(/Fwd R\/R\s*([\d.]+)/)?.[1] ?? null,
    price:    text.match(/(?:\$|£)[\d.]+(?:\/sh)?/)?.[0] ?? null,
    pctOfMax: text.match(/[+-]?\d+\.?\d*% of max/)?.[0] ?? null,
    strike:   text.match(/Strike \$([\d.]+)/)?.[1] ?? null,
    expiry:   text.match(/exp ([\w]+\s+\d+)/)?.[1] ?? null,
  }
}

function midCtx(stripped: string, duration: string | null, movement: string | null): string | null {
  if (!movement) return null
  const mIdx = stripped.indexOf(movement)
  if (mIdx <= 0) return null
  let between = stripped.slice(0, mIdx)
  if (duration) between = between.replace(new RegExp(`.*\\b${duration}\\b[^a-z]*`), '')
  return between.replace(/[.\s]+$/g, '').trim() || null
}

function formatNote(raw: string | null, strategy: string): string {
  if (!raw) return ''
  const p = parseNote(raw)
  switch (strategy) {
    case 'LDS': {
      const header = [p.structure, p.duration].filter(Boolean).join(' ')
      return [header || null, p.movement, p.fwdRR ? `R/R ${p.fwdRR}` : null].filter(Boolean).join('. ') || raw
    }
    case 'LEAP': {
      const stripped = raw.replace(/^LEAP\s+/, '')
      const ctx = midCtx(stripped, p.duration, p.movement)
      return [p.duration, ctx, p.movement].filter(Boolean).join('. ') || raw
    }
    case 'SWING': {
      const stripped = raw.replace(/^SWING\s+(?:single-leg\s+)?/, '')
      const ctx = midCtx(stripped, p.duration, p.movement)
      return [p.duration, ctx, p.movement, p.fwdRR ? `R/R ${p.fwdRR}` : null].filter(Boolean).join('. ') || raw
    }
    case '2x-ETF': {
      const ticker2x = raw.match(/^(2x\s+\w+)/)?.[1] ?? null
      return [ticker2x, p.movement].filter(Boolean).join('. ') || raw
    }
    case 'Thematic':
      return [p.price, p.movement].filter(Boolean).join('. ') || raw
    case 'WheelSP': {
      if (p.strike) {
        return [`@$${p.strike}${p.expiry ? ` ${p.expiry}` : ''}`, p.pctOfMax ?? p.movement]
          .filter(Boolean).join('. ')
      }
      return raw.replace(/^WheelSP on \w+\.\s*/, '')
    }
    case 'WheelSC': {
      const effCost = raw.match(/Eff cost \$([\d.]+)/)?.[1]
      const currentPx = raw.match(/Current \$([\d.]+)/)?.[1]
        ?? raw.match(/\b[A-Z]{2,6}\s+\$([\d.]+)\s*[—–]/)?.[1]
      if (effCost || currentPx) {
        return [effCost ? `Cost $${effCost}` : null, currentPx ? `$${currentPx} now` : null, p.pctOfMax]
          .filter(Boolean).join('. ')
      }
      return [p.price, p.movement].filter(Boolean).join('. ')
        || raw.replace(/^(?:NEW\s+)?WheelSC[^.]+\.\s*/, '')
    }
    default:
      return raw
  }
}

// ── Flag cell ─────────────────────────────────────────────────────────────────

function formalFlagColor(f: string): string {
  if (['UNDERWATER', 'WHEEL_STUCK'].includes(f))      return 'bg-red-500'
  if (['THESIS_CHECK', 'WHEEL_AT_RISK'].includes(f))  return 'bg-amber-400'
  if (['HARVEST'].includes(f))                         return 'bg-emerald-400'
  return 'bg-gray-500'
}

function inlineFlagColor(text: string): string {
  const t = text.toLowerCase()
  if (t.includes('violation') || t.includes('hard stop') || t.includes('exit') || t.includes('wheel-stuck')) return 'bg-red-500'
  if (t.includes('thesis') || t.includes('cut') || t.includes('warning') || t.includes('close'))             return 'bg-amber-400'
  if (t.includes('double') || t.includes('free-roll') || t.includes('execute'))                              return 'bg-emerald-400'
  return 'bg-gray-500'
}

interface FlagCellProps {
  flags: string[] | null
  inlineFlag: string | null
  onShow: (lines: string[], x: number, y: number) => void
  onHide: () => void
}

function FlagCell({ flags, inlineFlag, onShow, onHide }: FlagCellProps) {
  const hasFormal = flags && flags.length > 0
  if (!hasFormal && !inlineFlag) return <span className="text-gray-700">—</span>

  const lines = [
    ...(flags || []).map(f => f.replace(/_/g, ' ')),
    ...(inlineFlag ? [inlineFlag] : []),
  ]

  return (
    <div
      className="flex gap-1 items-center justify-center cursor-default"
      onMouseEnter={(e) => onShow(lines, e.clientX, e.clientY)}
      onMouseLeave={onHide}
    >
      {(flags || []).map((f, i) => (
        <span key={i} className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${formalFlagColor(f)}`} />
      ))}
      {!hasFormal && inlineFlag && (
        <span className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${inlineFlagColor(inlineFlag)}`} />
      )}
    </div>
  )
}

// ── Formatters ────────────────────────────────────────────────────────────────

function gainColor(v: number | null | undefined) {
  if (v == null) return ''
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-gray-400'
}

function fmtAvg(v: number | null | undefined) {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 100) return `$${n.toLocaleString('en-AU', { maximumFractionDigits: 0 })}`
  return `$${n.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function SortIcon({ dir }: { dir: SortDir }) {
  if (dir === 'asc')  return <span className="ml-1 opacity-80">↑</span>
  if (dir === 'desc') return <span className="ml-1 opacity-80">↓</span>
  return <span className="ml-1 opacity-20">↕</span>
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PositionsTable({ positions }: { positions: any[] }) {
  const [filter, setFilter]   = useState('')
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>(null)
  const [tip, setTip]         = useState<{ lines: string[]; x: number; y: number } | null>(null)

  function toggleSort(key: SortKey) {
    if (sortKey !== key) { setSortKey(key); setSortDir('asc'); return }
    if (sortDir === 'asc')  { setSortDir('desc'); return }
    setSortKey(null); setSortDir(null)
  }

  const rows = useMemo(() => {
    let r = positions ?? []
    if (filter.trim()) {
      const q = filter.toLowerCase()
      r = r.filter((p: any) =>
        p.symbol?.toLowerCase().includes(q) ||
        p.underlying?.toLowerCase().includes(q) ||
        p.theme?.toLowerCase().includes(q) ||
        p.strategy?.toLowerCase().includes(q)
      )
    }
    if (sortKey && sortDir) {
      r = [...r].sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey]
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv))
        return sortDir === 'asc' ? cmp : -cmp
      })
    }
    return r
  }, [positions, filter, sortKey, sortDir])

  function Th({ label, col, align = 'text-left' }: { label: string; col: SortKey; align?: string }) {
    return (
      <th
        onClick={() => toggleSort(col)}
        className={`px-4 py-3 ${align} cursor-pointer select-none hover:text-gray-300 transition-colors whitespace-nowrap`}
      >
        {label}<SortIcon dir={sortKey === col ? sortDir : null} />
      </th>
    )
  }

  return (
    <>
      {/* Fixed-position tooltip — position: fixed escapes all overflow clipping */}
      {tip && (
        <div
          className="fixed z-[9999] bg-gray-900 border border-gray-700 rounded-lg shadow-2xl px-3 py-2 text-xs text-gray-200 pointer-events-none max-w-[320px] leading-relaxed"
          style={{ left: tip.x + 14, top: tip.y + 10 }}
        >
          {tip.lines.map((l, i) => (
            <div key={i} className={i > 0 ? 'mt-1 pt-1 border-t border-gray-700' : ''}>{l}</div>
          ))}
        </div>
      )}

      <div className="px-4 py-2.5 border-b border-border flex items-center gap-2">
        <svg className="w-3.5 h-3.5 text-gray-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
        </svg>
        <input
          type="text"
          placeholder="Filter by symbol, underlying, theme or strategy…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="flex-1 bg-transparent text-sm text-gray-300 placeholder-gray-600 outline-none"
        />
        {filter && (
          <button onClick={() => setFilter('')} className="text-gray-600 hover:text-gray-400 text-xs">✕</button>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
              <Th label="Symbol"     col="symbol" />
              <Th label="Underlying" col="underlying" />
              <Th label="Theme"      col="theme" />
              <Th label="Strategy"   col="strategy" />
              <Th label="Qty"        col="qty"       align="text-right" />
              <Th label="Cost"       col="cost"      align="text-right" />
              <Th label="Avg"        col="avg_price" align="text-right" />
              <Th label="Value"      col="value"     align="text-right" />
              <Th label="Gain%"      col="gain_pct"  align="text-right" />
              <Th label="%NAV"       col="pct_nav"   align="text-right" />
              <th className="px-4 py-3 text-center text-xs text-gray-500 uppercase tracking-wider">Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((p: any, i: number) => {
              const { display: splitDisplay, flag: inlineFlag } = splitNote(p.csv_note)
              const formattedNote = formatNote(splitDisplay || null, p.strategy)
              return (
                <tr key={i} className="hover:bg-white/3 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex flex-col gap-0.5 w-[220px] min-w-0">
                      <span className="font-mono font-medium text-gray-200 leading-tight truncate">
                        {p.symbol}
                      </span>
                      {formattedNote && (
                        <span className="text-[10px] text-gray-500 leading-tight truncate" title={p.csv_note}>
                          {formattedNote}
                        </span>
                      )}
                      {p.ai_note && (
                        <span className="text-[10px] text-amber-500/70 leading-tight truncate" title={p.ai_note}>
                          ◈ {p.ai_note}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-gray-300 text-xs whitespace-nowrap">{p.underlying}</td>
                  <td className="px-4 py-2.5 text-gray-400 text-xs whitespace-nowrap">{p.theme ?? '—'}</td>
                  <td className="px-4 py-2.5 whitespace-nowrap">
                    <Badge value={p.strategy} />
                  </td>
                  <td className="px-4 py-2.5 text-right text-gray-300 whitespace-nowrap tabular-nums">{p.qty}</td>
                  <td className="px-4 py-2.5 text-right text-gray-300 whitespace-nowrap tabular-nums">${Number(p.cost).toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-right text-gray-400 whitespace-nowrap tabular-nums">{fmtAvg(p.avg_price)}</td>
                  <td className="px-4 py-2.5 text-right text-gray-300 whitespace-nowrap tabular-nums">${Number(p.value).toLocaleString()}</td>
                  <td className={`px-4 py-2.5 text-right font-medium whitespace-nowrap tabular-nums ${gainColor(p.gain_pct)}`}>
                    {p.gain_pct > 0 ? '+' : ''}{p.gain_pct}%
                  </td>
                  <td className="px-4 py-2.5 text-right text-gray-400 whitespace-nowrap tabular-nums">{p.pct_nav}%</td>
                  <td className="px-4 py-2.5 text-center">
                    <FlagCell
                      flags={p.flags}
                      inlineFlag={inlineFlag}
                      onShow={(lines, x, y) => setTip({ lines, x, y })}
                      onHide={() => setTip(null)}
                    />
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-8 text-center text-gray-600 text-xs">
                  No positions match
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}
