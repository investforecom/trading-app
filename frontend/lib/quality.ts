// Shared Quality Screen rating system — used by the interactive Quality
// Screen stage and the printable report so both grade metrics identically.
// green = good, yellow = mixed, red = weak, gray = not enough data / informational.

export type Rating = 'good' | 'neutral' | 'bad' | 'na'

export const RATING_DOT: Record<Rating, string> = {
  good: 'bg-emerald-400', neutral: 'bg-yellow-400', bad: 'bg-red-400', na: 'bg-gray-600',
}
export const RATING_TEXT: Record<Rating, string> = {
  good: 'text-emerald-400', neutral: 'text-yellow-400', bad: 'text-red-400', na: 'text-gray-500',
}

export function rateAbove(v: number | null | undefined, goodMin: number, neutralMin: number): Rating {
  if (v == null || Number.isNaN(v)) return 'na'
  return v >= goodMin ? 'good' : v >= neutralMin ? 'neutral' : 'bad'
}
export function rateBelow(v: number | null | undefined, goodMax: number, neutralMax: number): Rating {
  if (v == null || Number.isNaN(v)) return 'na'
  return v <= goodMax ? 'good' : v <= neutralMax ? 'neutral' : 'bad'
}
export function rateDilution(v: number | null | undefined): Rating {
  if (v == null || Number.isNaN(v)) return 'na'
  return v < 0 ? 'good' : v <= 0.02 ? 'neutral' : 'bad'
}
export function rateRelative(current: number | null | undefined, benchmark: number | null | undefined): Rating {
  if (current == null || benchmark == null || benchmark <= 0) return 'na'
  const ratio = current / benchmark
  return ratio <= 0.85 ? 'good' : ratio >= 1.15 ? 'bad' : 'neutral'
}

// Price multiples (P/E, EV/EBITDA, PEG, ...) flip meaning entirely once their
// denominator (earnings, EBITDA, growth) goes negative — a lower number no
// longer means "cheaper," it's just an artifact of unprofitability. Standard
// analyst convention is to call these "not meaningful" rather than grade them,
// so a non-positive value always reads as 'na' instead of accidentally
// scoring as cheap/good.
export function rateMultiple(v: number | null | undefined, goodMax: number, neutralMax: number): Rating {
  if (v != null && v <= 0) return 'na'
  return rateBelow(v, goodMax, neutralMax)
}
export function rateRelativeMultiple(current: number | null | undefined, benchmark: number | null | undefined): Rating {
  if (current != null && current <= 0) return 'na'
  return rateRelative(current, benchmark)
}

export function verdict(ratings: Rating[]): { label: string; color: string } {
  const rated = ratings.filter((r) => r !== 'na')
  if (rated.length === 0) return { label: 'Not enough data', color: 'text-gray-500' }
  const good = rated.filter((r) => r === 'good').length
  const bad = rated.filter((r) => r === 'bad').length
  if (good >= rated.length - bad && good > bad) return { label: 'Strong', color: 'text-emerald-400' }
  if (bad > good) return { label: 'Weak', color: 'text-red-400' }
  return { label: 'Mixed', color: 'text-yellow-400' }
}
