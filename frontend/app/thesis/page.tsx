'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

function fmtUsd(n: number | null | undefined) {
  if (n == null) return '—'
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function upsideColor(current: number | null, target: number | null) {
  if (current == null || target == null) return 'text-gray-500'
  return target > current ? 'text-emerald-400' : target < current ? 'text-red-400' : 'text-gray-400'
}

interface SearchResult {
  symbol: string
  name: string | null
  exchange: string | null
  type: string | null
  sector: string | null
}

// ── Ticker search (pre-search gate) ─────────────────────────────────────────
// Typing a bare ticker is ambiguous (AAPL vs. APLE, cross-listings on other
// exchanges, etc.) — this resolves the query against Yahoo Finance's search
// so the user picks the exact company/exchange before a thesis is built.

function TickerSearch({ onSelect }: { onSelect: (symbol: string) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      setSearching(false)
      return
    }
    setSearching(true)
    const handle = setTimeout(() => {
      api.thesis.search(q)
        .then((r) => { setResults(r); setOpen(true); setActiveIndex(-1) })
        .catch(() => setResults([]))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(handle)
  }, [query])

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  function choose(symbol: string) {
    setOpen(false)
    setQuery('')
    setResults([])
    onSelect(symbol)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open || results.length === 0) {
      if (e.key === 'Enter' && query.trim()) choose(query.trim().toUpperCase())
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter') {
      e.preventDefault()
      choose(activeIndex >= 0 ? results[activeIndex].symbol : query.trim().toUpperCase())
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={boxRef} className="relative">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder="Search by company name or ticker, e.g. Apple or AAPL"
        className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-blue-500"
        autoComplete="off"
      />

      {open && (
        <div className="absolute z-10 mt-1 w-full bg-card border border-border rounded-lg shadow-lg overflow-hidden max-h-80 overflow-y-auto">
          {searching && (
            <div className="px-3 py-2 text-xs text-gray-600">Searching…</div>
          )}
          {!searching && results.length === 0 && (
            <div className="px-3 py-2 text-xs text-gray-600">
              No matches — press Enter to try <span className="font-mono">{query.trim().toUpperCase()}</span> directly
            </div>
          )}
          {results.map((r, i) => (
            <button
              key={r.symbol + i}
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => choose(r.symbol)}
              className={`w-full flex items-center justify-between gap-3 px-3 py-2 text-left transition-colors ${
                i === activeIndex ? 'bg-blue-600/20' : 'hover:bg-white/5'
              }`}
            >
              <div className="min-w-0">
                <span className="font-mono font-semibold text-gray-100">{r.symbol}</span>
                <span className="text-xs text-gray-400 ml-2 truncate">{r.name}</span>
              </div>
              <div className="text-[10px] text-gray-600 flex-shrink-0 text-right">
                {r.exchange}{r.sector ? ` · ${r.sector}` : ''}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function ThesisIndexPage() {
  const router = useRouter()
  const [tickers, setTickers] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.thesis.tickers().then(setTickers).catch(() => setTickers([])).finally(() => setLoading(false))
  }, [])

  function goToTicker(symbol: string) {
    const clean = symbol.trim().toUpperCase()
    if (!clean) return
    router.push(`/thesis/${clean}`)
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-base font-semibold text-gray-100">Investment Thesis Builder</h1>
        <p className="text-xs text-gray-600 mt-0.5">
          Fundamentals + DCF (bear/base/bull) + AI-written thesis and risks, saved for later comparison.
        </p>
      </div>

      <TickerSearch onSelect={goToTicker} />

      <div>
        <h2 className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">Saved Theses</h2>
        {loading ? (
          <div className="text-xs text-gray-600 py-6 text-center">Loading…</div>
        ) : tickers.length === 0 ? (
          <div className="text-xs text-gray-600 py-6 text-center">No theses yet — search above to start one</div>
        ) : (
          <div className="bg-card border border-border rounded-xl overflow-hidden divide-y divide-border/50">
            {tickers.map((t) => (
              <button
                key={t.ticker}
                onClick={() => goToTicker(t.ticker)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors text-left"
              >
                <div>
                  <div className="font-mono font-semibold text-gray-100">{t.ticker}</div>
                  <div className="text-[10px] text-gray-600">
                    Updated {new Date(t.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-400">
                    Price {fmtUsd(t.current_price)}
                  </div>
                  <div className={`text-xs font-semibold ${upsideColor(t.current_price, t.target_price)}`}>
                    Target {fmtUsd(t.target_price)}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
