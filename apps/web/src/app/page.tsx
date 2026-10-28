import { Dashboard } from '@/components/dashboard/Dashboard'
import { EmptyState } from '@/components/Empty'
import { fetchDashboard } from '@/lib/api'

/**
 * Rendered per request. Every number on it is current or it is a lie.
 */
export const dynamic = 'force-dynamic'

export const metadata = { title: 'Dashboard — TrendForge' }

export default async function HomePage() {
  const data = await fetchDashboard()

  if (!data) {
    return (
      <div className="mx-auto max-w-2xl px-5 py-10">
        <EmptyState
          art="plug"
          title="The API is not answering, so there is nothing to show."
          hint="Start the stack and reload. Nothing on this page can be filled in from memory."
        />
      </div>
    )
  }

  return <Dashboard data={data} />
}
