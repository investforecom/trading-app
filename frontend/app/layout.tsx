import type { Metadata } from 'next'
import './globals.css'
import Sidebar from '@/components/layout/sidebar'
import SidebarStats from '@/components/layout/sidebar-stats'
import StatusBar from '@/components/layout/status-bar'

export const metadata: Metadata = {
  title: 'Trading Insights',
  description: 'Personal trading intelligence system',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden">
        <aside className="w-52 flex-shrink-0 bg-card border-r border-border flex flex-col overflow-hidden">
          <Sidebar />
          <SidebarStats />
          <div className="px-5 py-4 border-t border-border text-xs text-gray-600 flex-shrink-0">
            v1.0 · IBKR U15760849
          </div>
        </aside>
        <div className="flex-1 flex flex-col overflow-hidden">
          <StatusBar />
          <main className="flex-1 overflow-y-auto p-6 bg-surface">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}
