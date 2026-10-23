import type { Health, Region, TrendsResponse } from '@trendforge/types'

/**
 * Server-side API access. Every board page is a server component, so the
 * browser never talks to the API directly and there is no client-side fetch
 * waterfall on first paint.
 */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8020'

/** Boards change on a 30-minute beat; 60s keeps dev feeling live. */
const REVALIDATE = 60

class ApiUnavailable extends Error {}

async function get<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, { next: { revalidate: REVALIDATE } })
  } catch (cause) {
    // The API being down must render an explanatory board, not a stack trace.
    throw new ApiUnavailable(`cannot reach the API at ${BASE}`, { cause })
  }
  if (!response.ok) {
    throw new ApiUnavailable(`${path} returned ${response.status}`)
  }
  return (await response.json()) as T
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

export { ApiUnavailable }
