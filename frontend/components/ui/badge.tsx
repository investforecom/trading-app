interface BadgeProps { value: string }

const styles: Record<string, string> = {
  // Flag types
  ACTION:           'bg-red-500/15 text-red-400 border-red-500/30',
  WATCH:            'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  INFO:             'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  HARVEST:          'bg-orange-500/15 text-orange-400 border-orange-500/30',
  TRIM:             'bg-orange-500/15 text-orange-400 border-orange-500/30',
  UNDERWATER:       'bg-red-500/15 text-red-400 border-red-500/30',
  'WHEEL-STUCK':    'bg-red-500/15 text-red-400 border-red-500/30',
  'WHEEL-AT-RISK':  'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  'THESIS-CHECK':   'bg-blue-500/15 text-blue-400 border-blue-500/30',
  // Strategies
  LEAP:             'bg-indigo-500/15 text-indigo-400 border-indigo-500/30',
  LDS:              'bg-violet-500/15 text-violet-400 border-violet-500/30',
  SWING:            'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  '2x-ETF':         'bg-orange-500/15 text-orange-400 border-orange-500/30',
  Thematic:         'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
  WheelSP:          'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  WheelSC:          'bg-teal-500/15 text-teal-400 border-teal-500/30',
}

export default function Badge({ value }: BadgeProps) {
  const cls = styles[value] ?? 'bg-gray-500/15 text-gray-400 border-gray-500/30'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>
      {value}
    </span>
  )
}
