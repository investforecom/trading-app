import type { Metadata, Viewport } from 'next'
import './globals.css'
import AppShell from '@/components/layout/app-shell'
import Sidebar from '@/components/layout/sidebar'
import SidebarStats from '@/components/layout/sidebar-stats'
import StatusBar from '@/components/layout/status-bar'

export const metadata: Metadata = {
  title: 'Trading Insights',
  description: 'Personal trading intelligence system',
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden">
        <AppShell
          sidebar={
            <>
              <Sidebar />
              <SidebarStats />
              <div className="px-5 py-4 border-t border-border text-xs text-gray-600 flex-shrink-0">
                v1.0 · IBKR U15760849
              </div>
            </>
          }
          statusBar={<StatusBar />}
        >
          {children}
        </AppShell>
      </body>
    </html>
  )
}
