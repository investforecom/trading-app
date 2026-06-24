'use client'
import { useState, useEffect, useCallback, useRef } from 'react'

interface LogData {
  lines: string[]
  running: boolean
  last_run: string | null
  last_status: string | null
  total_lines: number
}

function lineColor(line: string): string {
  if (line.includes('[ERROR  ]')) return 'text-red-400'
  if (line.includes('[WARN   ]')) return 'text-yellow-400'
  if (line.includes('[OK     ]')) return 'text-emerald-400'
  if (line.includes('[PHASE  ]')) return 'text-blue-400 font-medium'
  if (line.includes('[START  ]') || line.includes('[END    ]')) return 'text-gray-500'
  return 'text-gray-400'
}

function parseSummary(line: string | null, running: boolean): string {
  if (!line) return 'No runs recorded yet'
  const ts  = line.match(/\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]/)?.[1] ?? '?'
  if (running) {
    const source = line.match(/source=(\w+)/)?.[1] ?? '?'
    return `Running since ${ts} · source=${source}`
  }
  const status  = line.match(/status=(\w+)/)?.[1] ?? '?'
  const elapsed = line.match(/elapsed=(\d+)s/)?.[1]
  return `${ts} · status=${status}${elapsed ? ` · ${elapsed}s` : ''}`
}

export default function LogViewer() {
  const [data,    setData]    = useState<LogData | null>(null)
  const [loading, setLoading] = useState(true)
  const [maxLines, setMaxLines] = useState(200)
  const bottomRef = useRef<HTMLDivElement>(null)
  const prevLen   = useRef(0)

  const reload = useCallback(async () => {
    try {
      const res = await fetch(`/api/system/logs?lines=${maxLines}`)
      if (res.ok) setData(await res.json())
    } finally {
      setLoading(false)
    }
  }, [maxLines])

  // Load on mount and when line limit changes
  useEffect(() => { reload() }, [reload])

  // Auto-poll every 5 s while a run is in progress
  useEffect(() => {
    if (!data?.running) return
    const id = setInterval(reload, 5000)
    return () => clearInterval(id)
  }, [data?.running, reload])

  // Scroll to bottom only when new lines are appended
  useEffect(() => {
    const len = data?.lines?.length ?? 0
    if (len > prevLen.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevLen.current = len
  }, [data?.lines?.length])

  if (loading) return <p className="text-gray-500 text-sm p-4">Loading…</p>
  if (!data)   return <p className="text-red-400 text-sm p-4">Failed to load logs.</p>

  const hasError = data.last_status === 'ERROR' ||
    (!data.running && data.lines.some(l => l.includes('[ERROR  ]')))

  const bannerClass = data.running
    ? 'bg-blue-600/15 border-blue-500/30 text-blue-300'
    : hasError
      ? 'bg-red-600/15 border-red-500/30 text-red-300'
      : 'bg-emerald-600/10 border-emerald-500/30 text-emerald-300'

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">

      {/* ── Status banner ─────────────────────────────────────────────── */}
      <div className={`rounded-lg border px-4 py-2.5 flex items-center justify-between gap-4 ${bannerClass}`}>
        <div className="flex items-center gap-2 min-w-0">
          {data.running && (
            <span className="flex-shrink-0 w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
          )}
          <span className="text-sm truncate">
            {parseSummary(data.last_run, data.running)}
          </span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <select
            value={maxLines}
            onChange={e => setMaxLines(Number(e.target.value))}
            className="bg-black/30 text-xs text-gray-400 border border-gray-700 rounded px-1.5 py-0.5 outline-none"
          >
            <option value={100}>100 lines</option>
            <option value={200}>200 lines</option>
            <option value={500}>500 lines</option>
            <option value={2000}>2000 lines</option>
          </select>
          <button
            onClick={reload}
            title="Refresh log"
            className="text-sm text-gray-400 hover:text-gray-100 transition-colors"
          >
            ⟳ Refresh
          </button>
        </div>
      </div>

      {/* ── Log lines ─────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-y-auto rounded-lg bg-black/50 border border-border">
        <pre className="p-4 text-[11px] leading-5 whitespace-pre-wrap break-all">
          {data.lines.length === 0 ? (
            <span className="text-gray-600">
              No entries yet. Logs appear here after the first manual refresh or cron run.
            </span>
          ) : (
            data.lines.map((line, i) => (
              <span key={i} className={`block ${lineColor(line)}`}>{line}</span>
            ))
          )}
          <div ref={bottomRef} />
        </pre>
      </div>

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <p className="text-[10px] text-gray-600 flex justify-between px-0.5">
        <span>{data.total_lines.toLocaleString()} total lines · showing last {maxLines}</span>
        <span>
          ~/logs/routine.log
          {data.running ? ' · auto-refreshing every 5 s' : ''}
        </span>
      </p>

    </div>
  )
}
