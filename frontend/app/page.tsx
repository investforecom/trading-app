import { api } from '@/lib/api'
import StatCard from '@/components/ui/stat-card'
import Badge from '@/components/ui/badge'

function fmt(n: number | null | undefined, prefix = '') {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const s = abs >= 1000 ? `${prefix}${(abs / 1000).toFixed(1)}k` : `${prefix}${abs}`
  return n < 0 ? `-${s}` : s
}

function fmtUSD(n: number | null | undefined) { return fmt(n, '$') }
function gainColor(v: number | null | undefined) {
  if (v == null) return ''
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-gray-400'
}

export default async function TradingPage() {
  const [summary, pnl, positions, flags, wheel] = await Promise.all([
    api.portfolio.summary(),
    api.portfolio.pnl(),
    api.portfolio.positions(),
    api.portfolio.flags(),
    api.portfolio.wheel(),
  ])

  return (
    <div className="space-y-8 max-w-7xl mx-auto">

      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Trading</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {summary?.date ? new Date(summary.date).toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' }) : '—'}
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="NAV"
          value={summary?.nav ? `$${Number(summary.nav).toLocaleString('en-AU', { maximumFractionDigits: 0 })}` : '—'} />
        <StatCard label="Deployed"
          value={summary?.deployed_pct != null ? `${summary.deployed_pct}%` : '—'}
          sub={summary?.deployed ? fmtUSD(summary.deployed) : undefined} />
        <StatCard label="YTD P&L"
          value={fmtUSD(pnl?.ytd)}
          color={pnl?.ytd > 0 ? 'green' : pnl?.ytd < 0 ? 'red' : 'default'} />
        <StatCard label="MTD P&L"
          value={fmtUSD(pnl?.mtd)}
          color={pnl?.mtd > 0 ? 'green' : pnl?.mtd < 0 ? 'red' : 'default'}
          sub={`${pnl?.ytd_trades ?? 0} trades YTD`} />
      </div>

      {/* Active Flags */}
      {flags && flags.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Active Flags</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Type</th>
                  <th className="px-4 py-3 text-left">Ticker</th>
                  <th className="px-4 py-3 text-left">Note</th>
                  <th className="px-4 py-3 text-left">Your Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {flags.map((f: any, i: number) => (
                  <tr key={i} className="hover:bg-white/3 transition-colors">
                    <td className="px-4 py-3"><Badge value={f.type} /></td>
                    <td className="px-4 py-3 font-mono font-medium text-gray-200">{f.ticker}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{f.note ?? '—'}</td>
                    <td className="px-4 py-3 text-blue-400 text-xs italic">{f.user_note ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Open Positions */}
      <section>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Positions <span className="text-gray-600 font-normal">({positions?.length ?? 0})</span>
        </h2>
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Symbol</th>
                  <th className="px-4 py-3 text-left">Strategy</th>
                  <th className="px-4 py-3 text-right">Cost</th>
                  <th className="px-4 py-3 text-right">Value</th>
                  <th className="px-4 py-3 text-right">Gain%</th>
                  <th className="px-4 py-3 text-right">%NAV</th>
                  <th className="px-4 py-3 text-left">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {positions?.map((p: any, i: number) => (
                  <tr key={i} className="hover:bg-white/3 transition-colors">
                    <td className="px-4 py-2.5 font-mono font-medium text-gray-200">{p.symbol}</td>
                    <td className="px-4 py-2.5 text-gray-400">{p.strategy}</td>
                    <td className="px-4 py-2.5 text-right text-gray-300">${Number(p.cost).toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right text-gray-300">${Number(p.value).toLocaleString()}</td>
                    <td className={`px-4 py-2.5 text-right font-medium ${gainColor(p.gain_pct)}`}>
                      {p.gain_pct > 0 ? '+' : ''}{p.gain_pct}%
                    </td>
                    <td className="px-4 py-2.5 text-right text-gray-400">{p.pct_nav}%</td>
                    <td className="px-4 py-2.5 text-xs text-blue-400 italic max-w-xs truncate">{p.note ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Wheel Positions */}
      {wheel && wheel.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Wheel Positions</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Underlying</th>
                  <th className="px-4 py-3 text-left">Symbol</th>
                  <th className="px-4 py-3 text-left">Type</th>
                  <th className="px-4 py-3 text-right">Cost</th>
                  <th className="px-4 py-3 text-right">Value</th>
                  <th className="px-4 py-3 text-right">Gain%</th>
                  <th className="px-4 py-3 text-right">Assign $</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {wheel.map((w: any, i: number) => (
                  <tr key={i} className="hover:bg-white/3 transition-colors">
                    <td className="px-4 py-2.5 font-mono font-medium text-gray-200">{w.underlying}</td>
                    <td className="px-4 py-2.5 text-gray-400 text-xs">{w.symbol}</td>
                    <td className="px-4 py-2.5"><Badge value={w.strategy} /></td>
                    <td className="px-4 py-2.5 text-right text-gray-300">${Number(w.cost).toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right text-gray-300">${Number(w.value).toLocaleString()}</td>
                    <td className={`px-4 py-2.5 text-right font-medium ${gainColor(w.gain_pct)}`}>
                      {w.gain_pct > 0 ? '+' : ''}{w.gain_pct}%
                    </td>
                    <td className="px-4 py-2.5 text-right text-gray-400">
                      {w.assignment_price ? `$${w.assignment_price}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
