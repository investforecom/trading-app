'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const nav = [
  { href: '/',          label: 'Positions',      icon: '📊' },
  { href: '/briefing',  label: 'Daily Briefing', icon: '📋' },
  { href: '/analytics', label: 'Analytics',      icon: '📈' },
  { href: '/weekly',    label: 'Weekly',         icon: '🔍' },
  { href: '/logs',      label: 'System Logs',    icon: '⚙️' },
]

export default function Sidebar() {
  const path = usePathname()
  return (
    <>
      <div className="px-5 py-5 border-b border-border flex-shrink-0">
        <span className="text-sm font-semibold text-gray-200 tracking-wide">TRADING INSIGHTS</span>
      </div>
      <nav className="py-4 space-y-1 px-2">
        {nav.map(({ href, label, icon }) => {
          const active = path === href
          return (
            <Link key={href} href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                ${active
                  ? 'bg-blue-600/20 text-blue-400 font-medium'
                  : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'}`}>
              <span>{icon}</span>
              {label}
            </Link>
          )
        })}
      </nav>
    </>
  )
}
