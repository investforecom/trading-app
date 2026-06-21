import { api } from '@/lib/api'
import RefreshButton from '@/components/ui/refresh-button'

function fmtPnl(n: number | null | undefined) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const s = abs >= 1000 ? `${(abs / 1000).toFixed(1)}k` : `${Math.round(abs)}`
  return (n < 0 ? '-$' : '+$') + s
}

function pnlColor(n: number | null | undefined) {
  if (n == null) return 'text-gray-400'
  return n > 0 ? 'text-emerald-400' : n < 0 ? 'text-red-400' : 'text-gray-400'
}

function StatRow({ label, value, valueColor = 'text-gray-200', sub }: {
  label: string; value: string; valueColor?: string; sub?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium text-gray-500 uppercase tracking-widest leading-none">
        {label}
      </span>
      <span className={`text-sm font-bold tabular-nums leading-none ${valueColor}`}>
        {value}
      </span>
      {sub && (
        <span className="text-[10px] text-gray-600 leading-none">{sub}</span>
      )}
    </div>
  )
}

export default async function SidebarStats() {
  let pnl: any     = null
  let wheelStats: any = null
  let summary: any = null

  try {
    ;[pnl, wheelStats, summary] = await Promise.all([
      api.portfolio.pnl(),
      api.portfolio.wheelStats(),
      api.portfolio.summary(),
    ])
  } catch { /* DB not ready */ }

  const ytd        = pnl?.ytd != null ? fmtPnl(pnl.ytd) : '—'
  const mtd        = pnl?.mtd != null ? fmtPnl(pnl.mtd) : '—'
  const otmPremium = wheelStats?.otm_premium != null
    ? `$${Number(wheelStats.otm_premium).toLocaleString()}`
    : '—'

  let dataTime = '—'
  if (summary?.last_updated) {
    try {
      dataTime = new Date(summary.last_updated).toLocaleString('en-AU', {
        timeZone: 'Australia/Sydney',
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    } catch { /* leave as — */ }
  }

  return (
    <div className="mt-auto flex flex-col border-t border-border flex-shrink-0">

      {/* Performance metrics */}
      <div className="px-5 py-4 space-y-3">
        <p className="text-[10px] font-medium text-gray-600 uppercase tracking-widest">Performance</p>
        <StatRow label="YTD P&L"     value={ytd}        valueColor={pnlColor(pnl?.ytd)} />
        <StatRow label="MTD P&L"     value={mtd}        valueColor={pnlColor(pnl?.mtd)} />
        <StatRow label="OTM Premium" value={otmPremium} valueColor="text-emerald-400"
                 sub="if all options expire OTM" />
      </div>

      {/* IBKR data timestamp + refresh trigger */}
      <div className="px-5 py-3 border-t border-border">
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="text-[10px] font-medium text-gray-600 uppercase tracking-widest leading-none">
              IBKR data
            </span>
            <span className="text-[10px] text-gray-500 tabular-nums leading-none truncate">
              {dataTime}
            </span>
          </div>
          <RefreshButton />
        </div>
      </div>

    </div>
  )
}
