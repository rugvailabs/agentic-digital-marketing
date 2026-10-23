import type { Health, Region, TrendsResponse } from '@trendforge/types'

/**
 * Server-side API access. Every board page is a server component, so the
 * browser never talks to the API directly and there is no client-side fetch
 * waterfall on first paint.
 */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8020'

/** Boards change on a 30-minute beat; 60s keeps dev feeling live. */
const REVALIDATE = 60

/** Reaching the API failed, or it answered with something unusable. */
class ApiUnavailable extends Error {}

/**
 * A 200 whose body would not parse. Separate from ApiUnavailable because it
 * is retryable: the usual cause is Next's on-disk fetch cache handing back a
 * truncated body after `.next/cache` was deleted or half-written, and the API
 * itself is perfectly healthy.
 */
class MalformedResponse extends Error {}

async function fetchJson<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, init)
  } catch (cause) {
    // The API being down must render an explanatory board, not a stack trace.
    throw new ApiUnavailable(`cannot reach the API at ${BASE}`, { cause })
  }

  if (!response.ok) {
    throw new ApiUnavailable(`${path} returned ${response.status}`)
  }

  const body = await response.text()
  try {
    return JSON.parse(body) as T
  } catch (cause) {
    // Parse by hand rather than response.json(): this branch needs the body
    // length in the message, and an unguarded response.json() throws a bare
    // SyntaxError that escapes every handler here and renders as a blank 500.
    throw new MalformedResponse(`${path} returned ${body.length} bytes of non-JSON`, { cause })
  }
}

async function get<T>(path: string): Promise<T> {
  try {
    return await fetchJson<T>(path, { next: { revalidate: REVALIDATE } })
  } catch (error) {
    if (!(error instanceof MalformedResponse)) throw error

    // Re-fetch past the cache. A poisoned cache entry would otherwise keep
    // failing for the whole revalidate window while the API is fine.
    console.warn(`[api] ${error.message} — retrying without the fetch cache`)
    try {
      return await fetchJson<T>(path, { cache: 'no-store' })
    } catch (retryError) {
      if (retryError instanceof MalformedResponse) {
        throw new ApiUnavailable(retryError.message, { cause: retryError })
      }
      throw retryError
    }
  }
}

export async function fetchRegions(): Promise<Region[]> {
  return get<Region[]>('/regions')
}

export async function fetchTrends(region: string, limit = 20): Promise<TrendsResponse> {
  const params = new URLSearchParams({ region, limit: String(limit) })
  return get<TrendsResponse>(`/trends?${params}`)
}

export async function fetchHealth(): Promise<Health | null> {
  try {
    return await get<Health>('/health')
  } catch {
    // A dead API is a state the top bar renders, not an error it throws.
    return null
  }
}

export { ApiUnavailable, MalformedResponse }
