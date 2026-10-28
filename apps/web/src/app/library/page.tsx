import Link from 'next/link'

import { Library } from '@/components/Library'
import { fetchFacetsSafely, fetchLibrarySafely } from '@/lib/library'

export const metadata = { title: 'Library — TrendForge' }

/**
 * The first page is fetched on the server, like the board: the library is
 * the page a team opens in the morning, and a spinner followed by a
 * client-side fetch is a slower way to show the same list.
 *
 * Filtering after that happens in the client component — a filter change is
 * not a new page.
 */
export default async function LibraryPage() {
  const [page, facets] = await Promise.all([fetchLibrarySafely(), fetchFacetsSafely()])

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Link href="/" className="text-sm text-slate hover:text-ink">
        Back to the board
      </Link>

      <h1 className="mt-6 font-display text-[28px] leading-tight font-bold text-ink">Library</h1>
      <p className="mt-2 max-w-prose text-sm text-slate">
        Every post and reel this workspace has generated. Open one to edit it in the Desk, or move
        it along from here.
      </p>

      <Library initial={page} facets={facets} />
    </main>
  )
}
