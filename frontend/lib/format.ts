// Shared display-formatting helpers used across the Thesis Builder pages
// (main ticker page + the printable report). Kept dependency-free — pure
// functions only — so both pages can import from here without pulling in
// unrelated component code.

export function fmtUsd(n: number | null | undefined, decimals = 2) {
  if (n == null || Number.isNaN(n)) return '—'
  return `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`
}

export function fmtBig(n: number | null | undefined) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
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

// Trims a long company-description blob (e.g. Yahoo's longBusinessSummary,
// often 6-8 sentences) down to its first few sentences — a lightweight
// summary with no extra AI call.
export function summarizeBusiness(text: string | null | undefined, maxSentences = 6): string {
  if (!text) return ''
  const sentences = text.match(/[^.!?]+[.!?]+/g) ?? [text]
  return sentences.slice(0, maxSentences).join(' ').trim()
}
