interface BadgeProps { value: string }

const styles: Record<string, string> = {
  ACTION:        'bg-red-500/15 text-red-400 border-red-500/30',
  WATCH:         'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  INFO:          'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  HARVEST:       'bg-orange-500/15 text-orange-400 border-orange-500/30',
  TRIM:          'bg-orange-500/15 text-orange-400 border-orange-500/30',
  UNDERWATER:    'bg-red-500/15 text-red-400 border-red-500/30',
  'WHEEL-STUCK': 'bg-red-500/15 text-red-400 border-red-500/30',
  'WHEEL-AT-RISK': 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  'THESIS-CHECK':  'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

export default function Badge({ value }: BadgeProps) {
  const cls = styles[value] ?? 'bg-gray-500/15 text-gray-400 border-gray-500/30'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>
      {value}
    </span>
  )
}
