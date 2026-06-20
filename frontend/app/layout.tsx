import type { Metadata } from 'next'
import './globals.css'
import Sidebar from '@/components/layout/sidebar'

export const metadata: Metadata = {
  title: 'Trading Insights',
  description: 'Personal trading intelligence system',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6 bg-surface">
          {children}
        </main>
      </body>
    </html>
  )
}
