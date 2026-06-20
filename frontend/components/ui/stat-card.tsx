interface StatCardProps {
  label: string
  value: string | number | null | undefined
  sub?: string
  color?: 'default' | 'green' | 'red' | 'yellow'
}

const colors = {
  default: 'text-white',
  green:   'text-emerald-400',
  red:     'text-red-400',
  yellow:  'text-yellow-400',
}

export default function StatCard({ label, value, sub, color = 'default' }: StatCardProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${colors[color]}`}>{value ?? '—'}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  )
}
