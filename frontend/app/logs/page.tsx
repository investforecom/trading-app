import LogViewer from '@/components/ui/log-viewer'

export const metadata = { title: 'System Logs · Trading Insights' }

export default function LogsPage() {
  return (
    <div className="h-full flex flex-col gap-4 min-h-0">
      <div className="flex items-baseline justify-between flex-shrink-0">
        <h1 className="text-base font-semibold text-gray-100">System Logs</h1>
        <p className="text-xs text-gray-600">
          Cron · manual refresh · ~/logs/routine.log
        </p>
      </div>
      <div className="flex-1 min-h-0">
        <LogViewer />
      </div>
    </div>
  )
}
