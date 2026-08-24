// Server components need an absolute URL; browser calls use relative /api/*
const BASE = typeof window === 'undefined'
  ? (process.env.API_URL ?? 'http://api:8000')
  : ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json()
}

async function post(path: string, body: unknown): Promise<any> {
  const res = await fetch(`${BASE}/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API POST ${path} → ${res.status}`)
  return res.json()
}

async function del(path: string): Promise<any> {
  const res = await fetch(`${BASE}/api${path}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`API DELETE ${path} → ${res.status}`)
  return res.json()
}

export const api = {
  portfolio: {
    summary:    () => get<any>('/portfolio/summary'),
    pnl:        () => get<any>('/portfolio/pnl'),
    positions:  () => get<any[]>('/portfolio/positions'),
    themes:     () => get<any[]>('/portfolio/themes'),
    flags:      () => get<any[]>('/portfolio/flags'),
    wheel:      () => get<any[]>('/portfolio/wheel'),
    wheelStats: () => get<any>('/portfolio/wheel-stats'),
    upsertNote: (underlying: string, body: { note: string; suppress_flags?: string[]; snooze_until?: string | null }) =>
      post(`/portfolio/positions/${encodeURIComponent(underlying)}/note`, body),
    deleteNote: (underlying: string) =>
      del(`/portfolio/positions/${encodeURIComponent(underlying)}/note`),
    latestBriefing: () => get<any>('/portfolio/briefing/latest'),
    briefings:      () => get<any[]>('/portfolio/briefings'),
    briefingByDate: (date: string) => get<any>(`/portfolio/briefing/${date}`),
  },
  analytics: {
    scorecard:  () => get<any[]>('/analytics/scorecard'),
    monthly:    () => get<any[]>('/analytics/monthly'),
    byStrategy: () => get<any[]>('/analytics/by-strategy'),
  },
  insights: {
    latest:  () => get<any>('/insights/latest'),
    history: () => get<any[]>('/insights/history'),
  },
  system: {
    logs:         (lines = 200) => get<any>(`/system/logs?lines=${lines}`),
    bridgeStatus: ()            => get<any>('/system/bridge/status'),
  },
  thesis: {
    search:           (q: string)        => get<any[]>(`/thesis/search?q=${encodeURIComponent(q)}`),
    tickers:          ()                 => get<any[]>('/thesis/tickers'),
    history:          (ticker: string)   => get<any[]>(`/thesis/${encodeURIComponent(ticker)}/history`),
    run:              (id: number)       => get<any>(`/thesis/run/${id}`),
    // Cache-first — instant if already fetched for this ticker, otherwise pulls from yfinance once.
    fundamentals:     (ticker: string)   => get<any>(`/thesis/${encodeURIComponent(ticker)}/fundamentals`),
    // Force a live re-pull, bypassing the cache — the "Refresh Data" button. Always adds a new snapshot.
    refreshFundamentals: (ticker: string) => post(`/thesis/${encodeURIComponent(ticker)}/fetch`, {}),
    fundamentalsHistory: (ticker: string) => get<any[]>(`/thesis/${encodeURIComponent(ticker)}/fundamentals/history`),
    fundamentalsSnapshot: (ticker: string, id: number) => get<any>(`/thesis/${encodeURIComponent(ticker)}/fundamentals/snapshot/${id}`),
    generate:         (ticker: string, body: any) => post(`/thesis/${encodeURIComponent(ticker)}/generate`, body),
    // Cache-first Thesis stage read — resolves to null if nothing generated yet, instead of throwing.
    thesisQa:         async (ticker: string) => {
      try {
        return await get<any>(`/thesis/${encodeURIComponent(ticker)}/thesis-qa`)
      } catch (e: any) {
        if (String(e.message).includes('404')) return null
        throw e
      }
    },
    generateThesisQa: (ticker: string) => post(`/thesis/${encodeURIComponent(ticker)}/thesis-qa/generate`, {}),
    thesisQaHistory:  (ticker: string)   => get<any[]>(`/thesis/${encodeURIComponent(ticker)}/thesis-qa/history`),
    thesisQaSnapshot: (ticker: string, id: number) => get<any>(`/thesis/${encodeURIComponent(ticker)}/thesis-qa/snapshot/${id}`),
  },
}
