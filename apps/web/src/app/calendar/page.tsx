import Link from 'next/link'

import { Calendar } from '@/components/Calendar'
import { gridFor, today, windowFor } from '@/lib/calendar'
import { fetchLibrarySafely } from '@/lib/library'

/**
 * Rendered per request, not at build time.
 *
 * Next prerenders a page with no dynamic inputs, and these all read the
 * API — so a build would either bake in whatever the board said that
 * afternoon or, with no API reachable, fail outright. Which is what it did.
 */
export const dynamic = 'force-dynamic'

export const metadata = { title: 'Calendar — TrendForge' }

/**
 * The current month, fetched on the server so the grid arrives filled.
 *
 * The month is the default view: a week is what you work in and a month is
 * what you plan in, and this page is for planning. Changing view or window
 * refetches in the client component.
 */
export default async function CalendarPage() {
  const { from, to } = windowFor(gridFor('month', today()))
  const page = await fetchLibrarySafely({
    status: 'scheduled',
    scheduled_from: from,
    scheduled_to: to,
    limit: 200,
  })

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <Link href="/" className="text-sm text-slate hover:text-ink">
        Back to the board
      </Link>

      <h1 className="mt-6 font-display text-[28px] leading-tight font-bold text-ink">Calendar</h1>
      <p className="mt-2 max-w-prose text-sm text-slate">
        Everything with a time on it, in IST. Nothing publishes yet — scheduling stores when, and
        posting is still yours to do.
      </p>

      <Calendar initialItems={page.items} />
    </main>
  )
}
