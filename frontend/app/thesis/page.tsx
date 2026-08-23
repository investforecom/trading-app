'use client'

import { useState, useEffect } from 'react'
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

export default function ThesisIndexPage() {
  const router = useRouter()
  const [ticker, setTicker] = useState('')
  const [tickers, setTickers] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.thesis.tickers().then(setTickers).catch(() => setTickers([])).finally(() => setLoading(false))
  }, [])

  function goToTicker(t: string) {
    const clean = t.trim().toUpperCase()
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

      <form
        onSubmit={(e) => { e.preventDefault(); goToTicker(ticker) }}
        className="flex gap-2"
      >
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="Enter ticker, e.g. NVDA"
          className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-blue-500 font-mono uppercase"
        />
        <button
          type="submit"
          className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 transition-colors"
        >
          Start Thesis
        </button>
      </form>

      <div>
        <h2 className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">Saved Theses</h2>
        {loading ? (
          <div className="text-xs text-gray-600 py-6 text-center">Loading…</div>
        ) : tickers.length === 0 ? (
          <div className="text-xs text-gray-600 py-6 text-center">No theses yet — start one above</div>
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
