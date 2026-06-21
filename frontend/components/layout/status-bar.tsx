import { api } from '@/lib/api'
import LiveClock from './live-clock'

function fmtUSD(n: number | null | undefined) {
  if (n == null) return null
  const abs = Math.abs(n)
  const s = abs >= 1000 ? `$${(abs / 1000).toFixed(1)}k` : `$${Math.round(abs)}`
  return n < 0 ? `-${s}` : s
}

function fmtChange(change: number | null | undefined, pct: number | null | undefined) {
  if (change == null || pct == null) return null
  const sign = change >= 0 ? '+' : ''
  const abs = fmtUSD(Math.abs(change))
  return `${sign}${change >= 0 ? '' : '-'}${abs} (${sign}${pct}%)`
}

function changeColor(n: number | null | undefined) {
  if (n == null) return 'text-gray-500'
  return n > 0 ? 'text-emerald-500' : n < 0 ? 'text-red-500' : 'text-gray-500'
}

function levColor(n: number | null | undefined) {
  if (n == null) return 'text-gray-100'
  return n >= 1.5 ? 'text-red-400' : n >= 1.2 ? 'text-yellow-400' : 'text-emerald-400'
}

interface FieldProps {
  label: string
  value: string
  valueColor?: string
  sub?: string | null
  subColor?: string
}

function Field({ label, value, valueColor = 'text-gray-100', sub, subColor = 'text-gray-500' }: FieldProps) {
  return (
    <div className="flex flex-col gap-px">
      <span className="text-[10px] font-medium text-gray-500 uppercase tracking-widest leading-none">
        {label}
      </span>
      <span className={`text-sm font-bold tabular-nums leading-none ${valueColor}`}>
        {value}
      </span>
      {sub && (
        <span className={`text-[10px] tabular-nums leading-none ${subColor}`}>
          {sub}
        </span>
      )}
    </div>
  )
}

function Divider() {
  return <div className="w-px self-stretch bg-border mx-1" />
}

export default async function StatusBar() {
  let summary: any = null
  let wheelStats: any = null

  try {
    ;[summary, wheelStats] = await Promise.all([
      api.portfolio.summary(),
      api.portfolio.wheelStats(),
    ])
  } catch { /* DB not ready */ }

  const nav        = summary?.nav != null
    ? `$${Number(summary.nav).toLocaleString('en-AU', { maximumFractionDigits: 0 })}`
    : '—'
  // daily_pnl = sum of position price changes (matches IBKR "Daily P&L")
  const navChange  = fmtChange(summary?.daily_pnl, summary?.daily_pnl_pct)

  const deployedUSD = fmtUSD(summary?.deployed) ?? '—'
  const deployedPct = summary?.deployed_pct != null ? `${summary.deployed_pct}%` : null

  const cashUSD = summary?.total_cash != null
    ? `$${Number(summary.total_cash).toLocaleString('en-AU', { maximumFractionDigits: 0 })}`
    : '—'
  const cashPct = (summary?.total_cash != null && summary?.nav != null)
    ? `${(100 * summary.total_cash / summary.nav).toFixed(1)}%`
    : null

  const assignRisk = wheelStats?.assignment_risk != null ? fmtUSD(wheelStats.assignment_risk) ?? '—' : '—'

  // SP Lev = assign_risk / cash: how many times over do SP obligations exceed available cash
  const effLevNum = (wheelStats?.assignment_risk != null && summary?.total_cash != null && Number(summary.total_cash) > 0)
    ? Number(wheelStats.assignment_risk) / Number(summary.total_cash)
    : null
  const effLev = effLevNum != null ? `${effLevNum.toFixed(2)}x` : '—'

  return (
    <div className="flex-shrink-0 border-b border-border bg-card/80 backdrop-blur-sm
                    flex items-center gap-4 px-6 py-2.5">

      <Field
        label="NAV"
        value={nav}
        sub={navChange ?? undefined}
        subColor={changeColor(summary?.daily_pnl)}
      />

      <Divider />

      <Field
        label="Deployed"
        value={deployedUSD}
        sub={deployedPct ?? undefined}
      />

      <Field
        label="Cash"
        value={cashUSD}
        sub={cashPct ?? undefined}
      />

      <Divider />

      <Field
        label="Assign Risk"
        value={assignRisk}
      />

      <Field
        label="SP Lev"
        value={effLev}
        valueColor={levColor(effLevNum)}
      />

      {/* Live Sydney clock */}
      <div className="ml-auto flex flex-col gap-px items-end">
        <span className="text-[10px] font-medium text-gray-500 uppercase tracking-widest leading-none">Sydney</span>
        <span className="text-xs text-gray-400 tabular-nums leading-none"><LiveClock /></span>
      </div>

    </div>
  )
}
