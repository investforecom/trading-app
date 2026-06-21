'use client'

import { useState, useMemo, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useRouter } from 'next/navigation'
import Badge from '@/components/ui/badge'
import { api } from '@/lib/api'

type SortDir = 'asc' | 'desc' | null
type SortKey = 'symbol' | 'underlying' | 'theme' | 'strategy' | 'qty' | 'cost' | 'avg_price' | 'value' | 'gain_pct' | 'pct_nav' | 'daily_pp'

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
  moveAlerts: string[]   // e.g. ['▼ −8.2pp today', '▼ −12.4pp week']
  onShow: (lines: string[], x: number, y: number) => void
  onHide: () => void
}

function FlagCell({ flags, inlineFlag, moveAlerts, onShow, onHide }: FlagCellProps) {
  const hasFormal = flags && flags.length > 0
  const hasInline = !!inlineFlag
  const hasMoves  = moveAlerts.length > 0
  if (!hasFormal && !hasInline && !hasMoves) return <span className="text-gray-700">—</span>

  const lines = [
    ...(flags || []).map(f => f.replace(/_/g, ' ')),
    ...(hasInline ? [inlineFlag!] : []),
    ...moveAlerts,
  ]

  return (
    <div
      className="flex gap-1 items-center justify-center cursor-default"
      onMouseEnter={(e) => onShow(lines, e.clientX, e.clientY)}
      onMouseLeave={onHide}
    >
      {(flags || []).map((f, i) => (
        <span key={`f${i}`} className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${formalFlagColor(f)}`} />
      ))}
      {!hasFormal && hasInline && (
        <span className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${inlineFlagColor(inlineFlag!)}`} />
      )}
      {/* Move-alert dots: square shape to distinguish from fundamental flags */}
      {moveAlerts.map((m, i) => {
        const isDown = m.startsWith('▼')
        return (
          <span
            key={`m${i}`}
            className={`inline-block w-2.5 h-2.5 rounded-sm shrink-0 ${isDown ? 'bg-red-400' : 'bg-emerald-400'}`}
          />
        )
      })}
    </div>
  )
}

// ── Multi-select dropdown ─────────────────────────────────────────────────────

function MultiSelect({ label, options, selected, onToggle }: {
  label: string
  options: string[]
  selected: Set<string>
  onToggle: (v: string) => void
}) {
  const [open, setOpen]     = useState(false)
  const [search, setSearch] = useState('')
  const ref                 = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const count    = selected.size
  const filtered = options.filter(o => o.toLowerCase().includes(search.toLowerCase()))

  // Build button label: show first 2 selected values + overflow count
  const selArr   = [...selected]
  const btnLabel = count === 0
    ? label
    : selArr.slice(0, 2).join(', ') + (count > 2 ? ` +${count - 2}` : '')

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors ${
          count > 0
            ? 'bg-white/10 text-gray-100 border-white/20'
            : 'text-gray-400 border-gray-700 hover:border-gray-500 hover:text-gray-300'
        }`}
      >
        <span className="max-w-[180px] truncate">{btnLabel}</span>
        <svg
          className={`w-3 h-3 flex-shrink-0 text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute top-full mt-1 left-0 z-50 bg-gray-900 border border-gray-700 rounded-lg shadow-2xl min-w-[190px] flex flex-col">
          {options.length > 7 && (
            <div className="px-3 pt-2 pb-1">
              <input
                type="text"
                placeholder="Search…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full bg-gray-800 text-xs text-gray-300 placeholder-gray-600 px-2 py-1 rounded border border-gray-700 outline-none"
                autoFocus
              />
            </div>
          )}
          <div className="overflow-y-auto max-h-[260px] py-1">
            {filtered.map(o => (
              <label key={o} className="flex items-center gap-2.5 px-3 py-1.5 hover:bg-white/5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.has(o)}
                  onChange={() => onToggle(o)}
                  className="accent-indigo-500 w-3.5 h-3.5 flex-shrink-0"
                />
                <span className="text-xs text-gray-300">{o}</span>
              </label>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-xs text-gray-600">No matches</div>
            )}
          </div>
          {count > 0 && (
            <div className="border-t border-gray-700/60 px-3 py-1.5">
              <button
                onClick={() => { onToggle('__clear__'); setOpen(false) }}
                className="text-[11px] text-gray-500 hover:text-gray-300 transition-colors"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DAILY_VIOLENT  = 5   // pp threshold for daily violent-move flag
const WEEKLY_VIOLENT = 10  // pp threshold for weekly violent-move flag

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

// Parse the "was X.X%" pattern from note as fallback when DB daily_pp is null
function parseDailyPP(gainPct: number | null, csvNote: string | null): number | null {
  if (gainPct == null || !csvNote) return null
  const m = csvNote.match(/\(was\s+([+-]?\d+\.?\d*)%\)/)
  if (!m) return null
  const prev = parseFloat(m[1])
  return Math.round((gainPct - prev) * 10) / 10
}

function deltaColor(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 7)  return v > 0 ? 'text-emerald-300 font-semibold' : 'text-red-300 font-semibold'
  if (abs >= 3)  return v > 0 ? 'text-emerald-400' : 'text-red-400'
  if (abs >= 1)  return v > 0 ? 'text-emerald-500' : 'text-red-500'
  return v > 0 ? 'text-emerald-700' : 'text-red-700'
}

function fmtDelta(v: number): string {
  return (v > 0 ? '+' : '') + v.toFixed(1) + '%'
}

function SortIcon({ dir }: { dir: SortDir }) {
  if (dir === 'asc')  return <span className="ml-1 opacity-80">↑</span>
  if (dir === 'desc') return <span className="ml-1 opacity-80">↓</span>
  return <span className="ml-1 opacity-20">↕</span>
}

// ── Shared context line ───────────────────────────────────────────────────────
// Priority: user ack note > amber flags > grey formatted note > null

function contextLine(p: any): { text: string; isFlag: boolean } | null {
  // User's acknowledgement note takes priority — shown in grey (conscious decision)
  if (p.note) return { text: p.note, isFlag: false }

  const { display: splitDisplay, flag: inlineFlag } = splitNote(p.csv_note)
  const note = formatNote(splitDisplay || null, p.strategy)

  const flagParts: string[] = [
    ...(p.flags ?? []).map((f: string) => f.replace(/_/g, ' ')),
    ...(inlineFlag ? [inlineFlag] : []),
    ...(p.eff_daily_pp != null && Math.abs(p.eff_daily_pp) >= DAILY_VIOLENT
      ? [`${p.eff_daily_pp > 0 ? '▲' : '▼'} ${fmtDelta(p.eff_daily_pp)} today`] : []),
    ...(p.weekly_pp != null && Math.abs(p.weekly_pp) >= WEEKLY_VIOLENT
      ? [`${p.weekly_pp > 0 ? '▲' : '▼'} ${fmtDelta(p.weekly_pp)} this week`] : []),
  ]

  if (flagParts.length > 0) return { text: flagParts.join(' · '), isFlag: true }
  if (note)                  return { text: note,                  isFlag: false }
  return null
}

// ── Note modal ────────────────────────────────────────────────────────────────

interface NoteModalProps {
  underlying: string
  formalFlags: string[]     // current p.flags for suppress pre-fill
  existingNote: string | null
  onClose: () => void
  onSaved: () => void
}

function NoteModal({ underlying, formalFlags, existingNote, onClose, onSaved }: NoteModalProps) {
  const [note,   setNote]   = useState(existingNote ?? '')
  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState<string | null>(null)

  async function handleSave() {
    const trimmed = note.trim()
    if (!trimmed) return
    setSaving(true)
    setError(null)
    try {
      await api.portfolio.upsertNote(underlying, {
        note: trimmed,
        suppress_flags: formalFlags,
      })
      onSaved()
    } catch {
      setError('Save failed — check connection')
      setSaving(false)
    }
  }

  async function handleClear() {
    setSaving(true)
    setError(null)
    try {
      await api.portfolio.deleteNote(underlying)
      onSaved()
    } catch {
      setError('Clear failed — check connection')
      setSaving(false)
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') onClose()
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSave()
  }

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-end sm:items-center justify-center" onKeyDown={onKeyDown}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Sheet — slides up from bottom on mobile, centered dialog on sm+ */}
      <div className="relative z-10 bg-gray-900 border border-gray-700 rounded-t-2xl sm:rounded-xl shadow-2xl
                      w-full sm:max-w-md mx-0 sm:mx-4 p-5 flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-gray-100 font-mono">{underlying}</span>
            {formalFlags.length > 0 && (
              <div className="flex gap-1.5 flex-wrap">
                {formalFlags.map(f => (
                  <span key={f} className="text-[10px] bg-amber-400/15 text-amber-400 px-1.5 py-0.5 rounded font-mono">
                    {f.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-600 hover:text-gray-400 transition-colors text-xl leading-none flex-shrink-0 mt-0.5"
          >
            ×
          </button>
        </div>

        {/* Textarea */}
        <textarea
          autoFocus
          rows={4}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200
                     placeholder-gray-600 resize-none outline-none focus:border-gray-500 transition-colors"
          placeholder="Your plan — e.g. 'Already trimmed 50% in strength. Waiting for weakness before cutting more.'"
          value={note}
          onChange={e => setNote(e.target.value)}
        />

        {error && <p className="text-xs text-red-400">{error}</p>}

        {/* Actions */}
        <div className="flex items-center justify-between gap-3">
          {existingNote ? (
            <button
              onClick={handleClear}
              disabled={saving}
              className="text-xs text-gray-600 hover:text-red-400 transition-colors disabled:opacity-40"
            >
              Clear note
            </button>
          ) : <div />}
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !note.trim()}
              className="px-4 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded-lg
                         transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving…' : existingNote ? 'Update' : 'Save'}
            </button>
          </div>
        </div>

        <p className="text-[10px] text-gray-700 -mt-1">⌘↵ to save · Esc to close</p>
      </div>
    </div>,
    document.body
  )
}

// ── Mobile card ───────────────────────────────────────────────────────────────

function PositionCard({ p, onEdit }: { p: any; onEdit: () => void }) {
  const dailyPP: number | null = p.eff_daily_pp
  const ctx = contextLine(p)

  return (
    <div className="px-4 py-2.5 border-b border-border last:border-0">
      {/* Row 1: badge + symbol + edit + %NAV */}
      <div className="flex items-center gap-2">
        <Badge value={p.strategy} />
        <span className="font-mono font-medium text-gray-100 text-sm leading-tight truncate flex-1 min-w-0">
          {p.symbol}
        </span>
        <button
          onClick={onEdit}
          className="text-gray-700 hover:text-gray-400 transition-colors flex-shrink-0 px-1 py-0.5 text-xs"
          title="Add / edit note"
        >
          ✎
        </button>
        <span className="text-[10px] text-gray-600 tabular-nums flex-shrink-0">{p.pct_nav}%</span>
      </div>

      {/* Row 2: one context line — wraps freely on mobile */}
      {ctx && (
        <p className={`text-[11px] mt-1 leading-snug ${ctx.isFlag ? 'text-amber-400/80' : 'text-gray-500'}`}>
          {ctx.text}
        </p>
      )}

      {/* Row 3: key metrics */}
      <div className="flex items-end gap-4 mt-2">
        <div>
          <div className="text-[9px] text-gray-600 uppercase tracking-wider">Value</div>
          <div className="text-xs text-gray-200 tabular-nums font-medium">${Number(p.value).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[9px] text-gray-600 uppercase tracking-wider">Gain</div>
          <div className={`text-xs tabular-nums font-medium ${gainColor(p.gain_pct)}`}>
            {p.gain_pct > 0 ? '+' : ''}{p.gain_pct}%
          </div>
        </div>
        {dailyPP != null && (
          <div>
            <div className="text-[9px] text-gray-600 uppercase tracking-wider">Day</div>
            <div className={`text-xs tabular-nums ${deltaColor(dailyPP)}`}>
              {fmtDelta(dailyPP)}{Math.abs(dailyPP) >= DAILY_VIOLENT ? ' ⚡' : ''}
            </div>
          </div>
        )}
        <div className="ml-auto text-right">
          <div className="text-[9px] text-gray-600 uppercase tracking-wider">Qty</div>
          <div className="text-xs text-gray-500 tabular-nums">{p.qty}</div>
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface NoteModalState {
  underlying: string
  formalFlags: string[]
  existingNote: string | null
}

export default function PositionsTable({ positions }: { positions: any[] }) {
  const router = useRouter()

  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>(null)
  const [tip,     setTip]     = useState<{ lines: string[]; x: number; y: number } | null>(null)
  const [noteModal, setNoteModal] = useState<NoteModalState | null>(null)

  const [selStrategies,  setSelStrategies]  = useState<Set<string>>(new Set())
  const [selThemes,      setSelThemes]      = useState<Set<string>>(new Set())
  const [selUnderlyings, setSelUnderlyings] = useState<Set<string>>(new Set())

  const allStrategies  = useMemo(() => [...new Set((positions ?? []).map((p: any) => p.strategy).filter(Boolean))].sort(), [positions])
  const allThemes      = useMemo(() => [...new Set((positions ?? []).map((p: any) => p.theme).filter(Boolean))].sort(), [positions])
  const allUnderlyings = useMemo(() => [...new Set((positions ?? []).map((p: any) => p.underlying).filter(Boolean))].sort(), [positions])

  const hasFilters = selStrategies.size > 0 || selThemes.size > 0 || selUnderlyings.size > 0

  function toggle(setter: React.Dispatch<React.SetStateAction<Set<string>>>, val: string) {
    if (val === '__clear__') { setter(new Set()); return }
    setter(prev => {
      const next = new Set(prev)
      next.has(val) ? next.delete(val) : next.add(val)
      return next
    })
  }

  function clearAll() {
    setSelStrategies(new Set())
    setSelThemes(new Set())
    setSelUnderlyings(new Set())
  }

  function toggleSort(key: SortKey) {
    if (sortKey !== key) { setSortKey(key); setSortDir('asc'); return }
    if (sortDir === 'asc') { setSortDir('desc'); return }
    setSortKey(null); setSortDir(null)
  }

  const rows = useMemo(() => {
    // Pre-compute effective daily_pp (DB value when available, else parse from note)
    // so filters AND sort both operate on the real value
    let r = (positions ?? []).map((p: any) => ({
      ...p,
      eff_daily_pp: p.daily_pp ?? parseDailyPP(p.gain_pct, p.csv_note),
    }))
    if (selStrategies.size  > 0) r = r.filter((p: any) => selStrategies.has(p.strategy))
    if (selThemes.size      > 0) r = r.filter((p: any) => selThemes.has(p.theme))
    if (selUnderlyings.size > 0) r = r.filter((p: any) => selUnderlyings.has(p.underlying))
    if (sortKey && sortDir) {
      r = [...r].sort((a: any, b: any) => {
        const av = sortKey === 'daily_pp' ? a.eff_daily_pp : a[sortKey]
        const bv = sortKey === 'daily_pp' ? b.eff_daily_pp : b[sortKey]
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv))
        return sortDir === 'asc' ? cmp : -cmp
      })
    }
    return r
  }, [positions, selStrategies, selThemes, selUnderlyings, sortKey, sortDir])

  const totals = useMemo(() => {
    const cost  = rows.reduce((s: number, p: any) => s + (Number(p.cost)    || 0), 0)
    const value = rows.reduce((s: number, p: any) => s + (Number(p.value)   || 0), 0)
    const pctNav = rows.reduce((s: number, p: any) => s + (Number(p.pct_nav) || 0), 0)
    const gainPct = cost > 0 ? (value - cost) / cost * 100 : null
    return { cost, value, pctNav, gainPct }
  }, [rows])

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

  function openNote(p: any) {
    setNoteModal({
      underlying:   p.underlying,
      formalFlags:  p.flags ?? [],
      existingNote: p.note ?? null,
    })
  }

  function onNoteSaved() {
    setNoteModal(null)
    router.refresh()
  }

  return (
    <>
      {/* Note modal */}
      {noteModal && (
        <NoteModal
          underlying={noteModal.underlying}
          formalFlags={noteModal.formalFlags}
          existingNote={noteModal.existingNote}
          onClose={() => setNoteModal(null)}
          onSaved={onNoteSaved}
        />
      )}

      {/* Portal tooltip */}
      {tip && createPortal(
        <div
          className="fixed z-[9999] bg-gray-900 border border-gray-700 rounded-lg shadow-2xl px-3 py-2 text-xs text-gray-200 pointer-events-none max-w-[320px] leading-relaxed"
          style={{ left: tip.x + 14, top: tip.y + 10 }}
        >
          {tip.lines.map((l, i) => (
            <div key={i} className={i > 0 ? 'mt-1 pt-1 border-t border-gray-700' : ''}>{l}</div>
          ))}
        </div>,
        document.body
      )}

      {/* Filter bar — single line */}
      <div className="px-4 py-2.5 border-b border-border flex items-center gap-2 flex-wrap">
        <MultiSelect
          label="Strategy"
          options={allStrategies}
          selected={selStrategies}
          onToggle={v => toggle(setSelStrategies, v)}
        />
        <MultiSelect
          label="Theme"
          options={allThemes}
          selected={selThemes}
          onToggle={v => toggle(setSelThemes, v)}
        />
        <MultiSelect
          label="Ticker"
          options={allUnderlyings}
          selected={selUnderlyings}
          onToggle={v => toggle(setSelUnderlyings, v)}
        />
        {hasFilters && (
          <>
            <span className="text-xs text-gray-600 ml-1">
              {rows.length} of {(positions ?? []).length}
            </span>
            <button
              onClick={clearAll}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors ml-auto"
            >
              Clear all
            </button>
          </>
        )}
      </div>

      {/* Mobile card list — shown on small screens */}
      <div className="md:hidden">
        {rows.map((p: any, i: number) => <PositionCard key={i} p={p} onEdit={() => openNote(p)} />)}
        {rows.length === 0 && (
          <div className="px-4 py-8 text-center text-gray-600 text-xs">No positions match</div>
        )}
        {/* Mobile total */}
        <div className="px-4 py-3 bg-white/[0.015] border-t-2 border-border/60 flex items-center justify-between gap-4">
          <span className="text-xs text-gray-500">
            Total ({rows.length}{hasFilters ? ` of ${(positions ?? []).length}` : ''})
          </span>
          <div className="flex gap-4">
            <div className="text-right">
              <div className="text-[9px] text-gray-600 uppercase tracking-wider">Cost</div>
              <div className="text-xs text-gray-300 tabular-nums font-semibold">${totals.cost.toLocaleString()}</div>
            </div>
            <div className="text-right">
              <div className="text-[9px] text-gray-600 uppercase tracking-wider">Value</div>
              <div className="text-xs text-gray-300 tabular-nums font-semibold">${totals.value.toLocaleString()}</div>
            </div>
            <div className="text-right">
              <div className="text-[9px] text-gray-600 uppercase tracking-wider">%NAV</div>
              <div className="text-xs text-gray-400 tabular-nums font-semibold">{totals.pctNav.toFixed(1)}%</div>
            </div>
          </div>
        </div>
      </div>

      {/* Desktop table — hidden on small screens */}
      <div className="hidden md:block overflow-x-auto">
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
              <Th label="Day Δ"      col="daily_pp"  align="text-right" />
              <Th label="%NAV"       col="pct_nav"   align="text-right" />
              <th className="px-4 py-3 text-center text-xs text-gray-500 uppercase tracking-wider">Flag</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-border">
            {rows.map((p: any, i: number) => {
              const { flag: inlineFlag } = splitNote(p.csv_note)

              const dailyPP: number | null  = p.eff_daily_pp
              const weeklyPP: number | null = p.weekly_pp ?? null

              // Flag-column dots + tooltip — independent of the symbol context line
              const moveAlerts: string[] = []
              if (dailyPP != null && Math.abs(dailyPP) >= DAILY_VIOLENT) {
                moveAlerts.push(`${dailyPP > 0 ? '▲' : '▼'} ${fmtDelta(dailyPP)} today`)
              }
              if (weeklyPP != null && Math.abs(weeklyPP) >= WEEKLY_VIOLENT) {
                moveAlerts.push(`${weeklyPP > 0 ? '▲' : '▼'} ${fmtDelta(weeklyPP)} this week`)
              }

              // Same rule as mobile cards: amber flag text when flagged, grey note otherwise
              const ctx = contextLine(p)

              return (
                <tr key={i} className="group hover:bg-white/3 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex flex-col gap-0.5 w-[220px] min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="font-mono font-medium text-gray-200 leading-tight truncate flex-1 min-w-0">
                          {p.symbol}
                        </span>
                        <button
                          onClick={() => openNote(p)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-600
                                     hover:text-gray-300 text-[11px] flex-shrink-0 leading-none"
                          title="Add / edit note"
                        >
                          ✎
                        </button>
                      </div>
                      {ctx && (
                        <span
                          className={`text-[10px] leading-tight truncate ${ctx.isFlag ? 'text-amber-400/80' : 'text-gray-500'}`}
                          title={ctx.text}
                        >
                          {ctx.text}
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
                  {/* Day Δ — daily movement with weekly sub-line */}
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    {dailyPP != null ? (
                      <div className="flex flex-col items-end gap-px">
                        <span className={`text-xs tabular-nums ${deltaColor(dailyPP)}`}>
                          {fmtDelta(dailyPP)}
                          {Math.abs(dailyPP) >= DAILY_VIOLENT ? ' ⚡' : ''}
                        </span>
                        {weeklyPP != null && (
                          <span className={`text-[10px] tabular-nums ${deltaColor(weeklyPP)}`}>
                            {fmtDelta(weeklyPP)}w
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-gray-700 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right text-gray-400 whitespace-nowrap tabular-nums">{p.pct_nav}%</td>
                  <td className="px-4 py-2.5 text-center">
                    <FlagCell
                      flags={p.flags}
                      inlineFlag={inlineFlag}
                      moveAlerts={moveAlerts}
                      onShow={(lines, x, y) => setTip({ lines, x, y })}
                      onHide={() => setTip(null)}
                    />
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={12} className="px-4 py-8 text-center text-gray-600 text-xs">
                  No positions match
                </td>
              </tr>
            )}
          </tbody>

          {/* Total row */}
          <tfoot>
            <tr className="border-t-2 border-border/60 bg-white/[0.015]">
              {/* colSpan=5 covers: Symbol | Underlying | Theme | Strategy | Qty */}
              <td className="px-4 py-2.5 text-xs text-gray-500 font-medium" colSpan={5}>
                Total
                <span className="text-gray-600 font-normal ml-1">
                  ({rows.length}{hasFilters ? ` of ${(positions ?? []).length}` : ''})
                </span>
              </td>
              <td className="px-4 py-2.5 text-right text-gray-300 tabular-nums text-xs font-semibold">
                ${totals.cost.toLocaleString()}
              </td>
              <td /> {/* Avg */}
              <td className="px-4 py-2.5 text-right text-gray-300 tabular-nums text-xs font-semibold">
                ${totals.value.toLocaleString()}
              </td>
              <td /> {/* Gain% */}
              <td /> {/* Day Δ */}
              <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums text-xs font-semibold">
                {totals.pctNav.toFixed(1)}%
              </td>
              <td /> {/* Flag */}
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  )
}
