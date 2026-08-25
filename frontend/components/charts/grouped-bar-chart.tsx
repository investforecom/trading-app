// Shared multi-series annual bar chart — used by the Quality Screen's
// "reliable growth" and "cash conversion" subsections, and reused as-is on
// the printable report's page 1. Diverges from a zero baseline so negative
// values (e.g. an unprofitable company's net income or FCF) visibly drop
// below the line instead of just shrinking toward the bottom of the chart.

import { fmtBig } from '@/lib/format'

export interface ChartSeries { key: string; label: string; color: string }

export function GroupedBarChart({ data, series }: { data: Record<string, any>[]; series: ChartSeries[] }) {
  if (!data || data.length < 2) return null
  const allValues = data.flatMap((d) => series.map((s) => d[s.key]))
  const min = Math.min(0, ...allValues)
  const max = Math.max(0, ...allValues)
  const range = max - min || 1
  const zeroPct = ((0 - min) / range) * 100

  return (
    <div className="px-4 pb-3 pt-2">
      <div className="flex items-stretch gap-3 h-28">
        {data.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col h-full">
            <div className="relative flex-1">
              <div className="absolute left-0 right-0 h-px bg-gray-600/50" style={{ bottom: `${zeroPct}%` }} />
              <div className="relative h-full flex items-stretch justify-center gap-0.5">
                {series.map((s) => {
                  const v = d[s.key]
                  const isNeg = v < 0
                  const heightPct = Math.max((Math.abs(v) / range) * 100, 1.5)
                  return (
                    <div key={s.key} className="flex-1 relative h-full">
                      <div
                        className="absolute w-full rounded-sm"
                        style={{
                          height: `${heightPct}%`,
                          bottom: isNeg ? `${Math.max(zeroPct - heightPct, 0)}%` : `${zeroPct}%`,
                          backgroundColor: s.color,
                          opacity: 0.8,
                        }}
                        title={`${s.label} ${d.fiscal_year_end.slice(0, 4)}: ${fmtBig(v)}`}
                      />
                    </div>
                  )
                })}
              </div>
            </div>
            <span className="text-[9px] text-gray-600 whitespace-nowrap text-center mt-1">{d.fiscal_year_end.slice(0, 4)}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 justify-center mt-2 flex-wrap">
        {series.map((s) => (
          <div key={s.key} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: s.color }} />
            <span className="text-[9px] text-gray-500">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
