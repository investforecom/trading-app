'use client'

import { useState, useEffect } from 'react'

interface AppShellProps {
  sidebar: React.ReactNode
  statusBar: React.ReactNode
  children: React.ReactNode
}

export default function AppShell({ sidebar, statusBar, children }: AppShellProps) {
  const [open, setOpen] = useState(true)

  // Close sidebar by default on mobile after first paint
  useEffect(() => {
    if (window.innerWidth < 768) setOpen(false)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden">

      {/* Sidebar — overflow-hidden clips content as width collapses */}
      <div className={`flex-shrink-0 overflow-hidden transition-[width] duration-200 ${open ? 'w-52' : 'w-0'}`}>
        <aside className="w-52 h-full bg-card border-r border-border flex flex-col overflow-hidden">
          {sidebar}
        </aside>
      </div>

      {/*
        Zero-width anchor. Sits between sidebar and main in the flex row,
        so it always tracks the right edge of the sidebar as it animates.
        overflow-visible lets the button poke out without affecting layout.
      */}
      <div className="relative flex-shrink-0 w-0 overflow-visible z-50">
        <button
          onClick={() => setOpen(o => !o)}
          title={open ? 'Collapse sidebar' : 'Expand sidebar'}
          className="absolute top-5 left-0 -translate-x-1/2
                     w-7 h-7 md:w-5 md:h-5 bg-card border border-border rounded-full
                     flex items-center justify-center
                     text-gray-500 hover:text-gray-300 hover:border-gray-500
                     text-[11px] transition-colors shadow-sm"
        >
          {open ? '‹' : '›'}
        </button>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {statusBar}
        <main className="flex-1 overflow-y-auto p-3 md:p-6 bg-surface [scrollbar-gutter:stable]">
          {children}
        </main>
      </div>

    </div>
  )
}
