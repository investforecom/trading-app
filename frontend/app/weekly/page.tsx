import { api } from '@/lib/api'
import Badge from '@/components/ui/badge'
import StatCard from '@/components/ui/stat-card'

export default async function WeeklyPage() {
  const [latest, history] = await Promise.all([
    api.insights.latest(),
    api.insights.history(),
  ])

  const { run, insights } = latest ?? {}
  const actions = insights?.filter((i: any) => i.severity === 'ACTION') ?? []
  const watches = insights?.filter((i: any) => i.severity === 'WATCH') ?? []
  const infos   = insights?.filter((i: any) => i.severity === 'INFO') ?? []

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Weekly Analysis</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {run?.run_date ? `Week of ${new Date(run.run_date).toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })}` : 'No analysis run yet'}
        </p>
      </div>

      {run && (
        <>
          {/* Severity counts */}
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Action Items" value={actions.length} color={actions.length > 0 ? 'red' : 'default'} />
            <StatCard label="Watching"     value={watches.length} color={watches.length > 0 ? 'yellow' : 'default'} />
            <StatCard label="Signals"      value={infos.length}   color="green" />
          </div>

          {/* Narrative summary */}
          {run.narrative && (
            <section>
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Summary</h2>
              <div className="bg-card border border-border rounded-xl p-5">
                <pre className="text-sm text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
                  {run.narrative}
                </pre>
              </div>
            </section>
          )}

          {/* Insights table */}
          <section>
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Findings</h2>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
                    <th className="px-4 py-3 text-left w-24">Level</th>
                    <th className="px-4 py-3 text-left w-28">Category</th>
                    <th className="px-4 py-3 text-left">Finding</th>
                    <th className="px-4 py-3 text-left">Detail</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {insights?.map((ins: any, i: number) => (
                    <tr key={i} className={`transition-colors
                      ${ins.severity === 'ACTION' ? 'bg-red-500/5 hover:bg-red-500/8' :
                        ins.severity === 'WATCH'  ? 'bg-yellow-500/5 hover:bg-yellow-500/8' :
                        'hover:bg-white/3'}`}>
                      <td className="px-4 py-3"><Badge value={ins.severity} /></td>
                      <td className="px-4 py-3 text-gray-400 text-xs font-medium">{ins.category}</td>
                      <td className="px-4 py-3 text-gray-200 font-medium">{ins.title}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs max-w-md">{ins.body}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* Run history */}
      {history && history.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">History</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Week</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                  <th className="px-4 py-3 text-right">Watches</th>
                  <th className="px-4 py-3 text-right">Signals</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {history.map((r: any, i: number) => (
                  <tr key={i} className="hover:bg-white/3 transition-colors">
                    <td className="px-4 py-2.5 text-gray-300">
                      {new Date(r.run_date).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <span className={r.actions > 0 ? 'text-red-400 font-medium' : 'text-gray-600'}>{r.actions}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <span className={r.watches > 0 ? 'text-yellow-400 font-medium' : 'text-gray-600'}>{r.watches}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <span className={r.infos > 0 ? 'text-emerald-400 font-medium' : 'text-gray-600'}>{r.infos}</span>
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
