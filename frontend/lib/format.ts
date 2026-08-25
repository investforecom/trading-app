// Shared display-formatting helpers used across the Thesis Builder pages
// (main ticker page + the printable report). Kept dependency-free — pure
// functions only — so both pages can import from here without pulling in
// unrelated component code.

export function fmtUsd(n: number | null | undefined, decimals = 2) {
  if (n == null || Number.isNaN(n)) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

export function fmtBig(n: number | null | undefined) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`
  return fmtUsd(n)
}

export function fmtPct(n: number | null | undefined, signed = false) {
  if (n == null || Number.isNaN(n)) return '—'
  const v = (n * 100).toFixed(1)
  return signed && n > 0 ? `+${v}%` : `${v}%`
}

export function fmtRatio(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—'
  return `${n.toFixed(2)}x`
}

// For price multiples (P/E, EV/EBITDA, PEG, ...) where a non-positive value
// means the underlying earnings/EBITDA/growth is negative — conventionally
// "not meaningful" rather than a real ratio to compare against.
export function fmtMultiple(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—'
  if (n <= 0) return 'N/M'
  return fmtRatio(n)
}

export function fmtShares(n: number | null | undefined) {
  if (n == null) return '—'
  return `${(n / 1e6).toFixed(0)}M`
}

export function upsideColor(current: number | null | undefined, target: number | null | undefined) {
  if (current == null || target == null) return 'text-gray-500'
  return target > current ? 'text-emerald-400' : target < current ? 'text-red-400' : 'text-gray-400'
}

export function vsCurrentPct(current: number | null | undefined, fv: number | null | undefined): string | undefined {
  if (current == null || fv == null || !current) return undefined
  return `${fmtPct(fv / current - 1, true)} vs current`
}
