'use client'
import { useState } from 'react'

type Phase = 'idle' | 'running' | 'done' | 'error'

export default function RefreshButton({ onDone }: { onDone?: () => void }) {
  const [phase,  setPhase]  = useState<Phase>('idle')
  const [status, setStatus] = useState('')

  function handleRefresh() {
    if (phase === 'running') return
    setPhase('running')
    setStatus('Starting...')

    const src = new EventSource('/api/system/refresh/stream')

    src.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)

        if (d.phase)  setStatus(d.phase)

        if (d.log) {
          // Show only the most meaningful part of each log line
          const clean = d.log.replace(/^\s*[→✓]\s*/, '').trim()
          if (clean) setStatus(clean)
        }

        if (d.done) {
          setPhase('done')
          setStatus('Updated ✓')
          src.close()
          setTimeout(() => window.location.reload(), 1200)
        }

        if (d.error) {
          setPhase('error')
          setStatus(d.error)
          src.close()
        }
      } catch { /* ignore parse errors */ }
    }

    src.onerror = () => {
      // SSE closes normally after stream ends — only flag error if not done
      if (phase !== 'done') {
        setPhase('error')
        setStatus('Connection lost')
      }
      src.close()
    }
  }

  const iconColor =
    phase === 'done'    ? 'text-emerald-400' :
    phase === 'error'   ? 'text-red-400'     :
    phase === 'running' ? 'text-blue-400'    :
    'text-gray-600 hover:text-gray-300'

  const spinning = phase === 'running'

  return (
    <div className="flex items-start gap-2 min-w-0">
      <button
        onClick={handleRefresh}
        disabled={phase === 'running'}
        title="Reload data from IBKR files"
        className={`flex-shrink-0 text-base leading-none transition-colors disabled:cursor-wait
          ${iconColor} ${spinning ? 'animate-spin' : ''}`}
      >
        ⟳
      </button>

      {status && (
        <span className={`text-[9px] leading-tight break-words min-w-0
          ${phase === 'error' ? 'text-red-400' : 'text-gray-500'}`}>
          {status}
        </span>
      )}
    </div>
  )
}
