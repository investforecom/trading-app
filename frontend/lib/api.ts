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
}
