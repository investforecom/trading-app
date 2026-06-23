import { api } from '@/lib/api'

// ── Markdown renderer ─────────────────────────────────────────────────────────
// Renders the briefing markdown format without an external library.

function renderInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**'))
      return <strong key={i} className="text-gray-100 font-semibold">{p.slice(2, -2)}</strong>
    if (p.startsWith('*') && p.endsWith('*'))
      return <em key={i} className="text-gray-300">{p.slice(1, -1)}</em>
    if (p.startsWith('`') && p.endsWith('`'))
      return <code key={i} className="text-xs bg-white/10 px-1 rounded font-mono">{p.slice(1, -1)}</code>
    return <span key={i}>{p}</span>
  })
}

function BriefingMd({ md }: { md: string }) {
  // Strip deployment-bands references before rendering
  const clean = md
    .split('\n')
    .map(line => {
      // Remove (band XX–YY%) from any line
      line = line.replace(/\s*\(band\s+[\d.]+[–\-][\d.]+%\)/g, '')
      // Remove deployment band commentary lines entirely
      if (/^⚠️\s*Deployed.*band/i.test(line)) return null
      if (/OVER-DEPLOYED flag/i.test(line)) {
        // Strip just the over-deployed mention from a larger sentence
        line = line.replace(/\s*\*?\*?OVER-DEPLOYED flag[^.]*\.\*?\*?/i, '').trim()
        if (!line || line === '>' || line === '> ') return null
      }
      // Strip blockquote lines that are purely about deployment bands
      if (line.startsWith('>') && /above the.*band/i.test(line) && !/NAV|P&L|margin/i.test(line))
        return null
      return line
    })
    .filter(l => l !== null)
    .join('\n')

  const lines = clean.split('\n')
  const nodes: React.ReactNode[] = []
  let inList = false

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    if (line.startsWith('# ')) {
      if (inList) { inList = false }
      nodes.push(
        <h1 key={i} className="text-base font-bold text-gray-100 mb-1 font-mono">
          {renderInline(line.slice(2))}
        </h1>
      )
      continue
    }

    if (line.startsWith('## ')) {
      if (inList) { inList = false }
      nodes.push(
        <h2 key={i} className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest mt-5 mb-2 border-b border-border pb-1">
          {line.slice(3)}
        </h2>
      )
      continue
    }

    if (line.startsWith('---')) {
      if (inList) { inList = false }
      nodes.push(<hr key={i} className="border-border my-3" />)
      continue
    }

    if (line.startsWith('> ')) {
      if (inList) { inList = false }
      nodes.push(
        <blockquote key={i} className="border-l-2 border-amber-500/40 pl-3 py-0.5 my-1.5 text-[11px] text-amber-400/70 leading-snug">
          {renderInline(line.slice(2))}
        </blockquote>
      )
      continue
    }

    if (line.match(/^[-*]\s/)) {
      if (!inList) { inList = true }
      nodes.push(
        <li key={i} className="text-xs text-gray-300 ml-4 my-0.5 leading-snug list-disc">
          {renderInline(line.slice(2))}
        </li>
      )
      continue
    }

    if (line.match(/^\d+\.\s/)) {
      if (!inList) { inList = true }
      nodes.push(
        <li key={i} className="text-xs text-gray-300 ml-4 my-0.5 leading-snug list-decimal">
          {renderInline(line.replace(/^\d+\.\s+/, ''))}
        </li>
      )
      continue
    }

    if (!line.trim()) {
      if (inList) inList = false
      nodes.push(<div key={i} className="h-1" />)
      continue
    }

    // Regular paragraph — includes **Header:** and **Wheel cover:** lines
    if (inList) inList = false
    nodes.push(
      <p key={i} className="text-xs text-gray-300 my-0.5 leading-snug">
        {renderInline(line)}
      </p>
    )
  }

  return <>{nodes}</>
}

// ── Date picker ───────────────────────────────────────────────────────────────

function fmt(d: string) {
  return new Date(d + 'T00:00:00').toLocaleDateString('en-AU', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function BriefingPage({
  searchParams,
}: {
  searchParams: { date?: string }
}) {
  let briefing: any = null
  let history: any[] = []

  try {
    ;[briefing, history] = await Promise.all([
      searchParams.date
        ? api.portfolio.briefingByDate(searchParams.date)
        : api.portfolio.latestBriefing(),
      api.portfolio.briefings(),
    ])
  } catch { /* DB not ready */ }

  return (
    <div className="flex gap-4 h-full overflow-hidden">

      {/* Date list sidebar */}
      <aside className="w-36 flex-shrink-0 overflow-y-auto border-r border-border pr-3">
        <p className="text-[9px] font-medium text-gray-600 uppercase tracking-widest mb-2 pt-1">History</p>
        {history.length === 0 && (
          <p className="text-[10px] text-gray-700">No briefings</p>
        )}
        {history.map((b: any) => {
          const isActive = b.date === (briefing?.date ?? history[0]?.date)
          return (
            <a
              key={b.date}
              href={`/briefing?date=${b.date}`}
              className={`block text-[11px] py-1 px-2 rounded mb-0.5 leading-tight transition-colors ${
                isActive
                  ? 'bg-blue-600/20 text-blue-400'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
              }`}
            >
              <span className="font-mono">{b.date}</span>
              {b.nav && (
                <span className="block text-[9px] text-gray-700">
                  ${Number(b.nav).toLocaleString('en-AU', { maximumFractionDigits: 0 })}
                </span>
              )}
            </a>
          )
        })}
      </aside>

      {/* Briefing content */}
      <main className="flex-1 overflow-y-auto">
        {!briefing ? (
          <div className="flex items-center justify-center h-full text-gray-600 text-xs">
            No briefing available yet
          </div>
        ) : (
          <div className="max-w-2xl">
            {/* Date header */}
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-border">
              <span className="text-[10px] text-gray-500">{fmt(briefing.date)}</span>
              <div className="flex items-center gap-3 text-[10px] text-gray-600">
                {briefing.nav && (
                  <span>NAV <span className="text-gray-400 tabular-nums">${Number(briefing.nav).toLocaleString('en-AU', { maximumFractionDigits: 0 })}</span></span>
                )}
                {briefing.eff_lev && (
                  <span>Eff Lev <span className={`tabular-nums ${Number(briefing.eff_lev) >= 1 ? 'text-red-400' : 'text-gray-400'}`}>{briefing.eff_lev}x</span></span>
                )}
              </div>
            </div>

            {/* Markdown body */}
            <article className="text-sm leading-relaxed">
              {briefing.briefing_md
                ? <BriefingMd md={briefing.briefing_md} />
                : <p className="text-gray-600 text-xs">No content.</p>
              }
            </article>
          </div>
        )}
      </main>

    </div>
  )
}
