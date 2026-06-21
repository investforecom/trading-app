// Server components need an absolute URL; browser calls use relative /api/*
const BASE = typeof window === 'undefined'
  ? (process.env.API_URL ?? 'http://api:8000')
  : ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json()
}

export const api = {
  portfolio: {
    summary:    () => get<any>('/portfolio/summary'),
    pnl:        () => get<any>('/portfolio/pnl'),
    positions:  () => get<any[]>('/portfolio/positions'),
    flags:      () => get<any[]>('/portfolio/flags'),
    wheel:      () => get<any[]>('/portfolio/wheel'),
    wheelStats: () => get<any>('/portfolio/wheel-stats'),
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
}
