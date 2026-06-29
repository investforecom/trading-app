import { api } from '@/lib/api'
import Badge from '@/components/ui/badge'
import PositionsTable from '@/components/ui/positions-table'

export default async function PositionsPage() {
  const [positions, flags] = await Promise.all([
    api.portfolio.positions(),
    api.portfolio.flags(),
  ])

  return (
    <div className="h-full flex flex-col gap-8">

      {/* Active Flags */}
      {flags && flags.length > 0 && (
        <section className="flex-shrink-0">
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

      {/* All Positions */}
      <section className="flex-1 flex flex-col min-h-0">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex-shrink-0">
          Positions <span className="text-gray-600 font-normal">({positions?.length ?? 0})</span>
        </h2>
        <div className="bg-card border border-border rounded-xl overflow-hidden flex-1 flex flex-col min-h-0">
          <PositionsTable positions={positions ?? []} />
        </div>
      </section>

    </div>
  )
}
