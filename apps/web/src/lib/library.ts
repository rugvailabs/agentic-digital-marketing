import type { EditorialStatus, LibraryFacets, LibraryPage } from '@trendforge/types'

/**
 * Library reads and the one write that moves an item along.
 *
 * Server-side for the page's first paint, client-side for a filter change —
 * which is why `BASE` is the public URL rather than an internal one. Both
 * sides call the same functions.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

/** Everything `GET /library` accepts, as the page spells it. */
export type LibraryFilters = {
  brand_id?: number
  region?: string
  language?: string
  kind?: string
  status?: EditorialStatus
  format?: string
  created_from?: string
  created_to?: string
  q?: string
  limit?: number
  offset?: number
}

/**
 * URLSearchParams, not template strings.
 *
 * An ISO timestamp ends in "+00:00" and a raw "+" in a query string is a
 * space, so a hand-built URL turns a date filter into a 422 about
 * "unexpected extra characters". This encodes.
 */
export function libraryQuery(filters: LibraryFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export async function fetchLibrary(filters: LibraryFilters = {}): Promise<LibraryPage> {
  const response = await fetch(`${API}/library${libraryQuery(filters)}`, { cache: 'no-store' })
  if (!response.ok) throw new Error(`/library returned ${response.status}`)
  return (await response.json()) as LibraryPage
}

export async function fetchFacets(): Promise<LibraryFacets> {
  const response = await fetch(`${API}/library/facets`, { cache: 'no-store' })
  if (!response.ok) throw new Error(`/library/facets returned ${response.status}`)
  return (await response.json()) as LibraryFacets
}

/** An empty library rather than a crash, for the page's first paint. */
export async function fetchLibrarySafely(filters: LibraryFilters = {}): Promise<LibraryPage> {
  try {
    return await fetchLibrary(filters)
  } catch {
    return { items: [], total: 0, limit: filters.limit ?? 50, offset: filters.offset ?? 0 }
  }
}

export async function fetchFacetsSafely(): Promise<LibraryFacets> {
  try {
    return await fetchFacets()
  } catch {
    return { brands: [], regions: [], languages: [], formats: [] }
  }
}

/**
 * Move an item along, or reschedule it.
 *
 * `scheduled_at` is sent only when it is part of the change: the API reads
 * an absent field as "leave it" and an explicit null as "clear it", and
 * dragging an item to another day must not also re-approve it.
 */
export async function moveJob(
  id: number,
  change: { editorial_status?: EditorialStatus; scheduled_at?: string | null },
): Promise<void> {
  const response = await fetch(`${API}/content/jobs/${id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(change),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `The API returned ${response.status}.`)
  }
}
