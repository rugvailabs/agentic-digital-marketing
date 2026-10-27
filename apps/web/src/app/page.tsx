import { Board } from '@/components/Board'
import { TopBar } from '@/components/TopBar'
import { Code, Empty } from '@/components/primitives'
import {
  ApiUnavailable,
  fetchBrands,
  fetchHealth,
  fetchPlatforms,
  fetchRegions,
  fetchTrends,
} from '@/lib/api'
import { SOURCE_NAMES, type SourceName } from '@trendforge/types'

const DEFAULT_REGION = 'IN'
const LADDER_LIMIT = 20

type Props = {
  searchParams: Promise<{ region?: string; limit?: string; platform?: string }>
}

export default async function BoardPage({ searchParams }: Props) {
  const { region = DEFAULT_REGION, limit, platform } = await searchParams
  const activePlatform = asPlatform(platform)
  const health = await fetchHealth()

  let content
  let regionName: string | undefined
  try {
    const [regions, board, brands, platforms] = await Promise.all([
      fetchRegions(),
      fetchTrends(region, clampLimit(limit), activePlatform),
      fetchBrands(),
      fetchPlatforms(),
    ])
    regionName = board.region.name
    content = (
      <Board
        regions={regions}
        board={board}
        brands={brands}
        platforms={platforms}
        activePlatform={activePlatform}
      />
    )
  } catch (error) {
    if (!(error instanceof ApiUnavailable)) throw error
    content = (
      <div className="p-6">
        <Empty
          title="The API is not answering."
          hint={
            <>
              Start the stack with <Code>.\tf.ps1 up</Code>, then <Code>.\tf.ps1 ingest</Code>.
              Checked <Code>{process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8020'}</Code>.
            </>
          }
        />
      </div>
    )
  }

  return (
    <main>
      <TopBar health={health} regionName={regionName} />
      {content}
    </main>
  )
}

function clampLimit(raw: string | undefined): number {
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) return LADDER_LIMIT
  // The API rejects anything outside 1..100 with a 422; clamp rather than
  // forwarding a bad value and rendering the unreachable-API state.
  return Math.min(100, Math.max(1, Math.trunc(parsed)))
}

/**
 * A `?platform=` the API would accept, or undefined.
 *
 * Validated here rather than forwarded: an unknown value is a 422 from the
 * API, which the board renders as "the API is not answering" — a misleading
 * page for what is really a bad link.
 */
function asPlatform(raw: string | undefined): SourceName | undefined {
  return SOURCE_NAMES.includes(raw as SourceName) ? (raw as SourceName) : undefined
}
