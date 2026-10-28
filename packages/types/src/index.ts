/**
 * Domain types for the TrendForge API.
 *
 * Everything here is derived from `src/generated/api.ts`, which is generated
 * from the FastAPI OpenAPI schema (`pnpm --filter @trendforge/types generate`).
 * Nothing is hand-written, so the web app cannot drift from the API: rename a
 * Pydantic model and this file fails to compile.
 */

import type { components, paths } from './generated/api'

type Schemas = components['schemas']

export type Region = Schemas['RegionOut']
export type RegionKind = Schemas['RegionKind']
export type Trend = Schemas['TrendOut']
export type TrendsResponse = Schemas['TrendsResponse']
export type IngestRunResponse = Schemas['IngestRunResponse']
export type Health = Schemas['Health']
export type Platform = Schemas['PlatformOut']
export type TrendPlatform = Schemas['TrendPlatformOut']
export type Brand = Schemas['BrandOut']
export type BrandIn = Schemas['BrandIn']
export type BrandPatch = Schemas['BrandPatch']
export type ContentJob = Schemas['JobOut']
export type ContentAsset = Schemas['AssetOut']
export type Language = Schemas['Language']
export type JobStatus = Schemas['JobStatus']
export type JobKind = Schemas['JobKind']
export type AssetKind = Schemas['AssetKind']
export type EditorialStatus = Schemas['EditorialStatus']
export type LibraryItem = Schemas['LibraryItem']
export type LibraryPage = Schemas['LibraryPage']
export type LibraryFacets = Schemas['LibraryFacets']

/**
 * In the order work moves through them, which is the order the filter chips
 * and the status menu are both drawn in. Taken from the schema, so adding a
 * state to the API fails the exhaustiveness check below rather than quietly
 * going unlisted.
 */
export const EDITORIAL_STATUSES = [
  'draft',
  'approved',
  'scheduled',
  'posted',
] as const satisfies readonly EditorialStatus[]

type EveryStatusListed =
  Exclude<EditorialStatus, (typeof EDITORIAL_STATUSES)[number]> extends never ? true : never
export const EDITORIAL_STATUSES_COVERED: EveryStatusListed = true

/** Sentence case, as CLAUDE.md asks. */
export const EDITORIAL_LABELS: Record<EditorialStatus, string> = {
  draft: 'Draft',
  approved: 'Approved',
  scheduled: 'Scheduled',
  posted: 'Posted',
}

/** Query parameters accepted by `GET /trends`. */
export type TrendsQuery = NonNullable<paths['/trends']['get']['parameters']['query']>

/** Query parameters accepted by `GET /library`. */
export type LibraryQuery = NonNullable<paths['/library']['get']['parameters']['query']>

/**
 * Platforms a topic can be attributed to.
 *
 * Taken from the generated schema rather than written out here. It used to be
 * a hand-kept array, and when the API gained `reddit` and `instagram` nothing
 * complained: the two lists were independent, so `SOURCE_LABELS` quietly
 * stopped covering every platform the board could return.
 */
export type SourceName = Schemas['SourceName']

/** In display order: discovery sources first, then the posting platforms. */
export const SOURCE_NAMES = [
  'google_trends',
  'google_news',
  'youtube',
  'reddit',
  'x',
  'instagram',
] as const satisfies readonly SourceName[]

/**
 * Fails to compile if the API gains a platform this array has not listed,
 * which is the guard the hand-kept version was missing.
 */
type EveryPlatformListed =
  Exclude<SourceName, (typeof SOURCE_NAMES)[number]> extends never ? true : never
export const PLATFORMS_COVERED: EveryPlatformListed = true

/** Short labels for the platform marks on a ladder row. */
export const SOURCE_LABELS: Record<SourceName, string> = {
  google_trends: 'Trends',
  google_news: 'News',
  youtube: 'YouTube',
  reddit: 'Reddit',
  x: 'X',
  instagram: 'Instagram',
}

/**
 * Two-letter marks for the ladder, where a row has room for provenance but
 * not for six words of it. Letters rather than icons: CLAUDE.md rules out an
 * icon beside every label, and a wire desk labels its sources in type.
 */
export const SOURCE_MARKS: Record<SourceName, string> = {
  google_trends: 'GT',
  google_news: 'GN',
  youtube: 'YT',
  reddit: 'RD',
  x: 'X',
  instagram: 'IG',
}

/**
 * The sparkline always receives exactly this many points — the API left-pads a
 * new topic with zeros, so the component never has to handle a short series.
 */
export const VELOCITY_POINTS = 6

export type { components, paths } from './generated/api'
