// Shared multi-series annual bar chart — used by the Quality Screen's
// "reliable growth" and "cash conversion" subsections, and reused as-is on
// the printable report's page 1.

import { fmtBig } from '@/lib/format'

export interface ChartSeries { key: string; label: string; color: string }

export function GroupedBarChart({ data, series }: { data: Record<string, any>[]; series: ChartSeries[] }) {
  if (!data || data.length < 2) return null
  const allValues = data.flatMap((d) => series.map((s) => d[s.key]))
  const min = Math.min(0, ...allValues)
  const max = Math.max(...allValues)
  const range = max - min || 1
  return (
    <div className="px-4 pb-3 pt-2">
      <div className="flex items-end gap-3 h-28">
        {data.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
            <div className="w-full flex items-end justify-center gap-0.5 h-full">
              {series.map((s) => {
                const v = d[s.key]
                const heightPct = Math.max(((v - min) / range) * 100, 2)
                return (
                  <div
                    key={s.key}
                    className="flex-1 rounded-t"
                    style={{ height: `${heightPct}%`, backgroundColor: s.color, opacity: 0.8 }}
                    title={`${s.label} ${d.fiscal_year_end.slice(0, 4)}: ${fmtBig(v)}`}
                  />
                )
              })}
            </div>
            <span className="text-[9px] text-gray-600 whitespace-nowrap">{d.fiscal_year_end.slice(0, 4)}</span>
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
