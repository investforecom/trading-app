import { api } from '@/lib/api'

export const metadata = { title: 'Themes · Trading Insights' }

// ── helpers ───────────────────────────────────────────────────────────────────

const DISPLAY_NAME: Record<string, string> = {
  'Software-Recovery': 'Software',
}
function displayName(theme: string) { return DISPLAY_NAME[theme] ?? theme }

function gainColor(pct: number | null) {
  if (pct == null) return 'text-gray-500'
  return pct > 0 ? 'text-emerald-400' : pct < 0 ? 'text-red-400' : 'text-gray-400'
}

function fmtPnl(n: number) {
  return `${n < 0 ? '-' : '+'}$${Math.abs(n).toLocaleString()}`
}

function fmtUsd(n: number) {
  return `$${Math.abs(n).toLocaleString()}`
}

function themeHex(theme: string): string {
  if (theme.startsWith('AI'))                              return '#3b82f6'
  if (theme.includes('Cloud'))                             return '#06b6d4'
  if (theme.includes('Large-Cap') || theme === 'Large-Cap-Tech') return '#6366f1'
  if (theme === 'Fintech')                                 return '#10b981'
  if (theme.includes('Nuclear'))                           return '#f59e0b'
  if (theme.includes('Solar'))                             return '#eab308'
  if (theme.includes('Battery'))                           return '#14b8a6'
  if (theme.includes('Nat-Gas'))                           return '#f97316'
  if (theme.includes('Drone') || theme.includes('Defense')) return '#f87171'
  if (theme.includes('Mineral'))                           return '#a8a29e'
  if (theme.includes('Consumer'))                          return '#f472b6'
  if (theme.includes('Edge') || theme.includes('HPC'))    return '#8b5cf6'
  if (theme.includes('Photon'))                            return '#d946ef'
  if (theme.includes('Software'))                          return '#818cf8'
  if (theme === 'Wheel-CC')                                return '#38bdf8'
  if (theme === 'Wheel-SP')                                return '#7dd3fc'
  if (theme === 'Cash')                                    return '#6b7280'
  return '#4b5563'
}

// ── ThemeCard (standard themes) ───────────────────────────────────────────────

function ThemeCard({ t, deployedNav }: { t: any; deployedNav: number }) {
  const pnlNum  = Number(t.pnl)
  const gainNum = Number(t.gain_pct)
  const navPct  = Number(t.pct_nav)
  const barPct  = deployedNav > 0 ? Math.min((navPct / deployedNav) * 100, 100) : 0
  const hex     = themeHex(t.theme)

  return (
    <div
      className="bg-card border border-border rounded-xl overflow-hidden flex flex-col"
      style={{ borderLeftColor: hex, borderLeftWidth: 3 }}
    >
      <div className="px-3 pt-2 pb-1 flex items-start justify-between gap-1">
        <div className="min-w-0">
          <div className="text-base font-semibold text-gray-100 truncate">{displayName(t.theme)}</div>
          <div className="text-[10px] text-gray-600 leading-tight">{t.tickers}t · {t.legs}L</div>
        </div>
        {t.theme === 'Cash' ? (
          <div className="text-right flex-shrink-0">
            <div className="text-xs font-semibold tabular-nums text-gray-400">{fmtUsd(t.value)}</div>
            <div className="text-[10px] tabular-nums leading-tight text-gray-600">{navPct}% NAV</div>
          </div>
        ) : (
          <div className="text-right flex-shrink-0">
            <div className={`text-xs font-semibold tabular-nums ${gainColor(gainNum)}`}>{fmtPnl(pnlNum)}</div>
            <div className={`text-[10px] tabular-nums leading-tight ${gainColor(gainNum)}`}>
              {gainNum > 0 ? '+' : ''}{gainNum}%
            </div>
          </div>
        )}
      </div>

      <div className="px-3 pb-1">
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <div className="h-full rounded-full" style={{ width: `${barPct}%`, backgroundColor: hex, opacity: 0.55 }} />
          </div>
          <span className="text-[10px] text-gray-500 tabular-nums w-10 text-right flex-shrink-0">{navPct}%</span>
        </div>
      </div>

      <div className="px-3 pb-1.5 flex gap-3 text-[10px] text-gray-500">
        <span>Cost <span className="text-gray-300 tabular-nums">{fmtUsd(t.cost)}</span></span>
        <span>Val <span className="text-gray-300 tabular-nums">{fmtUsd(t.value)}</span></span>
      </div>

      <div className="border-t border-border/50 divide-y divide-border/30">
        {(t.positions ?? []).map((p: any, i: number) => (
          <div key={i} className="px-3 py-0.5 flex items-center gap-1 text-[12px]">
            <span className="font-mono font-medium text-gray-200 w-12 truncate">{p.underlying}</span>
            <span className="text-[10px] text-gray-600 flex-1 truncate">{p.strategy}</span>
            <span className="tabular-nums text-gray-400 w-14 text-right">{fmtUsd(p.value)}</span>
            <span className={`tabular-nums w-11 text-right ${t.theme === 'Cash' ? 'text-gray-500' : gainColor(p.gain_pct)}`}>
              {t.theme === 'Cash'
                ? `${p.pct_nav}% NAV`
                : `${p.gain_pct > 0 ? '+' : ''}${p.gain_pct}%`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── WheelCCCard ───────────────────────────────────────────────────────────────

function WheelCCCard({ t, deployedNav }: { t: any; deployedNav: number }) {
  const hex    = themeHex('Wheel-CC')
  const navPct = Number(t.pct_nav)
  const barPct = deployedNav > 0 ? Math.min((navPct / deployedNav) * 100, 100) : 0

  const positions: any[] = t.positions ?? []
  const stocks = positions.filter(p => (p.symbol ?? '').endsWith('_STK'))
  const calls  = positions.filter(p => !(p.symbol ?? '').endsWith('_STK'))

  // Build per-underlying map
  const byUnderlying: Record<string, { stock: any; cc: any }> = {}
  for (const s of stocks) {
    byUnderlying[s.underlying] = { stock: s, cc: null }
  }
  for (const c of calls) {
    if (!byUnderlying[c.underlying]) byUnderlying[c.underlying] = { stock: null, cc: null }
    byUnderlying[c.underlying].cc = c
  }

  // P&L: stocks gain + CC premium decayed (short: profit = cost - value)
  const stockPnl = stocks.reduce((s, p) => s + (Number(p.value) - Number(p.cost)), 0)
  const ccPnl    = calls.reduce((s, p) => s + (Number(p.cost) - Number(p.value)), 0)
  const totalPnl = stockPnl + ccPnl

  return (
    <div
      className="bg-card border border-border rounded-xl overflow-hidden flex flex-col"
      style={{ borderLeftColor: hex, borderLeftWidth: 3 }}
    >
      {/* Header */}
      <div className="px-3 pt-2 pb-1 flex items-start justify-between gap-1">
        <div className="min-w-0">
          <div className="text-base font-semibold text-gray-100 truncate">Covered Calls</div>
          <div className="text-[10px] text-gray-600 leading-tight">
            {stocks.length} stocks · {calls.length} CC
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className={`text-xs font-semibold tabular-nums ${gainColor(totalPnl)}`}>
            {fmtPnl(totalPnl)}
          </div>
          <div className="text-[10px] tabular-nums leading-tight text-gray-600">{navPct}% NAV</div>
        </div>
      </div>

      {/* Bar */}
      <div className="px-3 pb-1">
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <div className="h-full rounded-full" style={{ width: `${barPct}%`, backgroundColor: hex, opacity: 0.55 }} />
          </div>
          <span className="text-[10px] text-gray-500 tabular-nums w-10 text-right flex-shrink-0">{navPct}%</span>
        </div>
      </div>

      {/* Stock value + CC premium totals */}
      <div className="px-3 pb-1.5 flex gap-3 text-[10px] text-gray-500">
        <span>Stocks <span className="text-gray-300 tabular-nums">
          {fmtUsd(stocks.reduce((s, p) => s + Number(p.value), 0))}
        </span></span>
        <span>CC risk <span className="text-gray-300 tabular-nums">
          {fmtUsd(calls.reduce((s, p) => s + Number(p.value), 0))}
        </span></span>
      </div>

      {/* Per-underlying rows: stock row + indented CC row */}
      <div className="border-t border-border/50 divide-y divide-border/30">
        {Object.entries(byUnderlying).map(([und, { stock, cc }]) => (
          <div key={und}>
            {stock && (
              <div className="px-3 py-0.5 flex items-center gap-1 text-[12px]">
                <span className="font-mono font-medium text-gray-200 w-12 truncate">{und}</span>
                <span className="text-[10px] text-gray-600 flex-1">stock</span>
                <span className="tabular-nums text-gray-400 w-14 text-right">{fmtUsd(stock.value)}</span>
                <span className={`tabular-nums w-11 text-right ${gainColor(stock.gain_pct)}`}>
                  {stock.gain_pct > 0 ? '+' : ''}{stock.gain_pct}%
                </span>
              </div>
            )}
            {cc && Number(cc.value) > 0 && (
              <div className="px-3 py-0.5 flex items-center gap-1 text-[11px] bg-white/[0.02]">
                <span className="text-sky-400/60 w-12 truncate pl-2">↳ CC</span>
                <span className="text-[10px] text-gray-700 flex-1">
                  {cc.strike ? `$${cc.strike} call` : 'call'}
                  {Number(cc.value) > Number(cc.cost)
                    ? <span className="text-red-400/70"> ITM</span>
                    : null}
                </span>
                <span className="tabular-nums text-sky-400/60 w-14 text-right">{fmtUsd(cc.value)}</span>
                <span className={`tabular-nums w-11 text-right ${gainColor(cc.gain_pct)}`}>
                  {cc.gain_pct > 0 ? '+' : ''}{cc.gain_pct}%
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── WheelSPCard ───────────────────────────────────────────────────────────────

function WheelSPCard({ t, deployedNav }: { t: any; deployedNav: number }) {
  const hex    = themeHex('Wheel-SP')
  const navPct = Number(t.pct_nav)
  const barPct = deployedNav > 0 ? Math.min((navPct / deployedNav) * 100, 100) : 0

  const positions: any[] = t.positions ?? []
  const totalPremiumRcvd = positions.reduce((s, p) => s + Number(p.cost), 0)
  const totalRemaining   = positions.reduce((s, p) => s + Number(p.value), 0)
  const totalAssignment  = positions.reduce((s, p) => s + Number(p.assignment_risk ?? 0), 0)
  const premiumDecayed   = totalPremiumRcvd - totalRemaining

  return (
    <div
      className="bg-card border border-border rounded-xl overflow-hidden flex flex-col"
      style={{ borderLeftColor: hex, borderLeftWidth: 3 }}
    >
      {/* Header */}
      <div className="px-3 pt-2 pb-1 flex items-start justify-between gap-1">
        <div className="min-w-0">
          <div className="text-base font-semibold text-gray-100 truncate">Cash Secured Puts</div>
          <div className="text-[10px] text-gray-600 leading-tight">
            {positions.length} puts · assign {fmtUsd(totalAssignment)}
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-xs font-semibold tabular-nums text-emerald-400">
            {fmtPnl(premiumDecayed)}
          </div>
          <div className="text-[10px] tabular-nums leading-tight text-gray-600">{navPct}% NAV</div>
        </div>
      </div>

      {/* Bar */}
      <div className="px-3 pb-1">
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <div className="h-full rounded-full" style={{ width: `${barPct}%`, backgroundColor: hex, opacity: 0.55 }} />
          </div>
          <span className="text-[10px] text-gray-500 tabular-nums w-10 text-right flex-shrink-0">{navPct}%</span>
        </div>
      </div>

      {/* Premium summary */}
      <div className="px-3 pb-1.5 flex gap-3 text-[10px] text-gray-500">
        <span>Rcvd <span className="text-gray-300 tabular-nums">{fmtUsd(totalPremiumRcvd)}</span></span>
        <span>Remain <span className="text-gray-300 tabular-nums">{fmtUsd(totalRemaining)}</span></span>
      </div>

      {/* Per-put rows */}
      <div className="border-t border-border/50 divide-y divide-border/30">
        {positions.map((p: any, i: number) => (
          <div key={i} className="px-3 py-0.5 flex items-center gap-1 text-[12px]">
            <span className="font-mono font-medium text-gray-200 w-12 truncate">{p.underlying}</span>
            <span className="text-[10px] text-gray-600 flex-1 truncate">
              {p.strike ? `$${p.strike}P` : 'put'}
              {p.assignment_risk ? ` · ${fmtUsd(p.assignment_risk)}` : ''}
            </span>
            <span className="tabular-nums text-gray-400 w-14 text-right">{fmtUsd(p.value)}</span>
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

  const active   = themes.filter(t =>
    t.theme !== 'Cash' && t.theme !== 'Untagged' &&
    t.theme !== 'Wheel-CC' && t.theme !== 'Wheel-SP'
  )
  const wheelCC  = themes.find(t => t.theme === 'Wheel-CC')
  const wheelSP  = themes.find(t => t.theme === 'Wheel-SP')
  const special  = themes.filter(t => t.theme === 'Cash' || t.theme === 'Untagged')

  const deployedNav = [
    ...active,
    ...(wheelCC ? [wheelCC] : []),
    ...(wheelSP ? [wheelSP] : []),
  ].reduce((s, t) => s + Number(t.pct_nav), 0)

  const totalPnl  = active.reduce((s, t) => s + Number(t.pnl), 0)
  const totalLegs = active.reduce((s, t) => s + t.legs, 0)

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

      {/* Active theme cards */}
      {active.length === 0 ? (
        <div className="text-xs text-gray-600 py-12 text-center">No theme data available</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {active.map(t => <ThemeCard key={t.theme} t={t} deployedNav={deployedNav} />)}
        </div>
      )}

      {/* Bottom row: Wheel CC / Wheel SP / Cash */}
      {(wheelCC || wheelSP || special.length > 0) && (
        <div>
          <div className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">Wheel &amp; Cash</div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {wheelCC && <WheelCCCard t={wheelCC} deployedNav={deployedNav} />}
            {wheelSP && <WheelSPCard t={wheelSP} deployedNav={deployedNav} />}
            {special.map(t => <ThemeCard key={t.theme} t={t} deployedNav={deployedNav} />)}
          </div>
        </div>
      )}
    </div>
  )
}
