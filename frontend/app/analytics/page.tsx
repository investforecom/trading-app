import { api } from '@/lib/api'
import StatCard from '@/components/ui/stat-card'
import PnlBarChart from '@/components/charts/pnl-bar'

function fmtUSD(n: number | null | undefined) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const s = abs >= 1000 ? `$${(abs / 1000).toFixed(1)}k` : `$${abs}`
  return n < 0 ? `-${s}` : s
}

export default async function AnalyticsPage() {
  const [scorecard, monthly, byStrategy] = await Promise.all([
    api.analytics.scorecard(),
    api.analytics.monthly(),
    api.analytics.byStrategy(),
  ])

  const totalYtd  = byStrategy?.reduce((s: number, r: any) => s + (r.ytd ?? 0), 0)
  const total1y   = byStrategy?.reduce((s: number, r: any) => s + (r.one_year ?? 0), 0)

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Analytics</h1>
        <p className="text-sm text-gray-500 mt-0.5">Strategy performance · Realized P&amp;L</p>
      </div>

      {/* Totals */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard label="YTD Total P&L" value={fmtUSD(totalYtd)}
          color={totalYtd > 0 ? 'green' : totalYtd < 0 ? 'red' : 'default'} />
        <StatCard label="1Y Total P&L"  value={fmtUSD(total1y)}
          color={total1y  > 0 ? 'green' : total1y  < 0 ? 'red' : 'default'} />
      </div>

      {/* Monthly P&L chart */}
      <section>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Monthly Realized P&amp;L</h2>
        <div className="bg-card border border-border rounded-xl p-4">
          <PnlBarChart data={monthly} />
        </div>
      </section>

      {/* Strategy scorecard */}
      <section>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Strategy Scorecard (1Y)</h2>
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3 text-left">Strategy</th>
                <th className="px-4 py-3 text-right">Trades</th>
                <th className="px-4 py-3 text-right">Win %</th>
                <th className="px-4 py-3 text-right">Avg Gain</th>
                <th className="px-4 py-3 text-right">YTD P&amp;L</th>
                <th className="px-4 py-3 text-right">1Y P&amp;L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {scorecard?.map((r: any, i: number) => (
                <tr key={i} className="hover:bg-white/3 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-gray-200">{r.strategy}</td>
                  <td className="px-4 py-2.5 text-right text-gray-400">{r.trades_1y}</td>
                  <td className="px-4 py-2.5 text-right text-gray-300">{r.win_rate ?? '—'}%</td>
                  <td className={`px-4 py-2.5 text-right font-medium ${r.avg_gain_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {r.avg_gain_pct > 0 ? '+' : ''}{r.avg_gain_pct}%
                  </td>
                  <td className={`px-4 py-2.5 text-right font-medium ${r.ytd_pnl > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {fmtUSD(r.ytd_pnl)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-medium ${r.pnl_1y > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {fmtUSD(r.pnl_1y)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
