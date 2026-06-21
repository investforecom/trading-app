'use client'

import { useState, useMemo } from 'react'
import Badge from '@/components/ui/badge'

type SortDir = 'asc' | 'desc' | null
type SortKey = 'underlying' | 'strategy' | 'cost' | 'value' | 'gain_pct' | 'assignment_price'

function gainColor(v: number | null | undefined) {
  if (v == null) return ''
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-gray-400'
}

function SortIcon({ dir }: { dir: SortDir }) {
  if (dir === 'asc')  return <span className="ml-1 opacity-80">↑</span>
  if (dir === 'desc') return <span className="ml-1 opacity-80">↓</span>
  return <span className="ml-1 opacity-20">↕</span>
}

export default function WheelTable({ wheel }: { wheel: any[] }) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>(null)

  function toggleSort(key: SortKey) {
    if (sortKey !== key) { setSortKey(key); setSortDir('asc'); return }
    if (sortDir === 'asc')  { setSortDir('desc'); return }
    setSortKey(null); setSortDir(null)
  }

  const rows = useMemo(() => {
    if (!sortKey || !sortDir) return wheel ?? []
    return [...(wheel ?? [])].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv))
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [wheel, sortKey, sortDir])

  function Th({ label, col, align = 'text-left' }: { label: string; col: SortKey; align?: string }) {
    return (
      <th
        onClick={() => toggleSort(col)}
        className={`px-4 py-3 ${align} cursor-pointer select-none hover:text-gray-300 transition-colors`}
      >
        {label}<SortIcon dir={sortKey === col ? sortDir : null} />
      </th>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-gray-500 uppercase tracking-wider">
            <Th label="Underlying"    col="underlying" />
            <th className="px-4 py-3 text-left text-xs text-gray-500 uppercase tracking-wider">Symbol</th>
            <Th label="Type"          col="strategy" />
            <Th label="Cost"          col="cost"              align="text-right" />
            <Th label="Value"         col="value"             align="text-right" />
            <Th label="Gain%"         col="gain_pct"          align="text-right" />
            <Th label="Assign $"      col="assignment_price"  align="text-right" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((w: any, i: number) => (
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
  )
}
