import { api } from '@/lib/api'

export const metadata = { title: 'Themes · Trading Insights' }

// ── helpers ───────────────────────────────────────────────────────────────────

const DISPLAY_NAME: Record<string, string> = {
  'Software-Recovery': 'Software',
  'Wheel':             'Wheel Income',
}
function displayName(theme: string) { return DISPLAY_NAME[theme] ?? theme }

function gainColor(pct: number | null) {
  if (pct == null) return 'text-gray-500'
  return pct > 0 ? 'text-emerald-400' : pct < 0 ? 'text-red-400' : 'text-gray-400'
}

function fmtPnl(n: number) {
  return `${n < 0 ? '-' : '+'}$${Math.abs(n).toLocaleString()}`
}

// Returns a CSS hex colour for the theme — used for both the left border and bar fill.
function themeHex(theme: string): string {
  if (theme.startsWith('AI'))                            return '#3b82f6' // blue
  if (theme.includes('Cloud'))                           return '#06b6d4' // cyan
  if (theme.includes('Large-Cap') || theme === 'Large-Cap-Tech') return '#6366f1' // indigo
  if (theme === 'Fintech')                               return '#10b981' // emerald
  if (theme.includes('Nuclear'))                         return '#f59e0b' // amber
  if (theme.includes('Solar'))                           return '#eab308' // yellow
  if (theme.includes('Battery'))                         return '#14b8a6' // teal
  if (theme.includes('Nat-Gas'))                         return '#f97316' // orange
  if (theme.includes('Drone') || theme.includes('Defense')) return '#f87171' // red
  if (theme.includes('Mineral'))                         return '#a8a29e' // stone
  if (theme.includes('Consumer'))                        return '#f472b6' // pink
  if (theme.includes('Edge') || theme.includes('HPC'))  return '#8b5cf6' // violet
  if (theme.includes('Photon'))                          return '#d946ef' // fuchsia
  if (theme.includes('Software'))                        return '#818cf8' // indigo-400
  if (theme === 'Wheel')                                 return '#38bdf8' // sky
  if (theme === 'Cash')                                  return '#6b7280' // gray
  return '#4b5563'
}

// ── ThemeCard ─────────────────────────────────────────────────────────────────

function ThemeCard({ t, deployedNav }: { t: any; deployedNav: number }) {
  const pnlNum  = Number(t.pnl)
  const gainNum = Number(t.gain_pct)
  const navPct  = Number(t.pct_nav)
  // bar = this theme's share of total deployed capital (0–100%)
  const barPct  = deployedNav > 0 ? Math.min((navPct / deployedNav) * 100, 100) : 0
  const hex     = themeHex(t.theme)

  return (
    <div
      className="bg-card border border-border rounded-xl overflow-hidden flex flex-col"
      style={{ borderLeftColor: hex, borderLeftWidth: 3 }}
    >
      {/* Header */}
      <div className="px-3 pt-2 pb-1 flex items-start justify-between gap-1">
        <div className="min-w-0">
          <div className="text-base font-semibold text-gray-100 truncate">{displayName(t.theme)}</div>
          <div className="text-[10px] text-gray-600 leading-tight">
            {t.tickers}t · {t.legs}L
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className={`text-xs font-semibold tabular-nums ${gainColor(gainNum)}`}>
            {fmtPnl(pnlNum)}
          </div>
          <div className={`text-[10px] tabular-nums leading-tight ${gainColor(gainNum)}`}>
            {gainNum > 0 ? '+' : ''}{gainNum}%
          </div>
        </div>
      </div>

      {/* Allocation bar — width = share of deployed capital */}
      <div className="px-3 pb-1">
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <div
              className="h-full rounded-full"
              style={{ width: `${barPct}%`, backgroundColor: hex, opacity: 0.55 }}
            />
          </div>
          <span className="text-[10px] text-gray-500 tabular-nums w-10 text-right flex-shrink-0">
            {navPct}%
          </span>
        </div>
      </div>

      {/* Cost / Value */}
      <div className="px-3 pb-1.5 flex gap-3 text-[10px] text-gray-500">
        <span>Cost <span className="text-gray-300 tabular-nums">${Number(t.cost).toLocaleString()}</span></span>
        <span>Val <span className="text-gray-300 tabular-nums">${Number(t.value).toLocaleString()}</span></span>
      </div>

      {/* Position legs */}
      <div className="border-t border-border/50 divide-y divide-border/30">
        {(t.positions ?? []).map((p: any, i: number) => (
          <div key={i} className="px-3 py-0.5 flex items-center gap-1 text-[11px]">
            <span className="font-mono font-medium text-gray-200 w-12 truncate">{p.underlying}</span>
            <span className="text-[9px] text-gray-600 flex-1 truncate">{p.strategy}</span>
            <span className="tabular-nums text-gray-400 w-14 text-right">${Number(p.value).toLocaleString()}</span>
            <span className={`tabular-nums w-11 text-right ${gainColor(p.gain_pct)}`}>
              {p.gain_pct > 0 ? '+' : ''}{p.gain_pct}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function ThemesPage() {
  let themes: any[] = []
  try { themes = await api.portfolio.themes() } catch { /* DB not ready */ }

  const active   = themes.filter(t => t.theme !== 'Cash' && t.theme !== 'Untagged' && t.theme !== 'Wheel')
  const wheel    = themes.find(t => t.theme === 'Wheel')
  const special  = themes.filter(t => t.theme === 'Cash' || t.theme === 'Untagged')

  // Sum of % NAV across all non-cash positions (the denominator for bars)
  const deployedNav = [...active, ...(wheel ? [wheel] : [])].reduce((s, t) => s + Number(t.pct_nav), 0)
  const totalPnl    = active.reduce((s, t) => s + Number(t.pnl), 0)
  const totalLegs   = active.reduce((s, t) => s + t.legs, 0)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-base font-semibold text-gray-100">Theme Allocation</h1>
          <p className="text-xs text-gray-600 mt-0.5">
            {active.length} themes · {totalLegs} legs ·{' '}
            <span className={gainColor(totalPnl)}>{fmtPnl(totalPnl)}</span>
            {' '}unrealized · bar = share of {deployedNav.toFixed(1)}% deployed
          </p>
        </div>
      </div>

      {/* Theme cards — 2 cols md, 3 cols lg, 4 cols xl */}
      {active.length === 0 ? (
        <div className="text-xs text-gray-600 py-12 text-center">No theme data available</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {active.map(t => <ThemeCard key={t.theme} t={t} deployedNav={deployedNav} />)}
        </div>
      )}

      {/* Wheel Income + Cash + Untagged — all in one bottom row */}
      {(wheel || special.length > 0) && (
        <div>
          <div className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">Wheel &amp; Cash</div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {wheel && <ThemeCard t={wheel} deployedNav={deployedNav} />}
            {special.map(t => <ThemeCard key={t.theme} t={t} deployedNav={deployedNav} />)}
          </div>
        </div>
      )}
    </div>
  )
}
