import { Empty } from '@/components/primitives'

export const metadata = { title: 'Offline — TrendForge' }

/**
 * What the service worker serves when a navigation finds no network.
 *
 * Deliberately not a cached board. A trend desk showing yesterday's ranks
 * without saying so is worse than one that says it cannot reach the
 * network: the whole product is a claim about what is happening right now.
 */
export default function OfflinePage() {
  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <h1 className="font-display text-[28px] leading-tight font-bold text-ink">You are offline</h1>
      <div className="mt-6">
        <Empty
          title="The board is live data, so there is nothing useful to show from memory."
          hint="Reload when you have a connection and the ladder will be current."
        />
      </div>
    </main>
  )
}
