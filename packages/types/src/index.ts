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
export type Brand = Schemas['BrandOut']
export type ContentJob = Schemas['JobOut']
export type ContentAsset = Schemas['AssetOut']
export type Language = Schemas['Language']
export type JobStatus = Schemas['JobStatus']
export type JobKind = Schemas['JobKind']
export type AssetKind = Schemas['AssetKind']

/** Query parameters accepted by `GET /trends`. */
export type TrendsQuery = NonNullable<paths['/trends']['get']['parameters']['query']>

/** Source names the merge can attribute a topic to. */
export const SOURCE_NAMES = ['google_trends', 'google_news', 'youtube', 'x'] as const
export type SourceName = (typeof SOURCE_NAMES)[number]

/** Short labels for the source chips on a ladder row. */
export const SOURCE_LABELS: Record<SourceName, string> = {
  google_trends: 'Trends',
  google_news: 'News',
  youtube: 'YouTube',
  x: 'X',
}

/**
 * The sparkline always receives exactly this many points — the API left-pads a
 * new topic with zeros, so the component never has to handle a short series.
 */
export const VELOCITY_POINTS = 6

export type { components, paths } from './generated/api'
