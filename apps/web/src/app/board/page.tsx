import { Board } from '@/components/Board'
import { Code, Empty } from '@/components/ui'
import { ApiUnavailable, fetchBrands, fetchPlatforms, fetchRegions, fetchTrends } from '@/lib/api'
import { SOURCE_NAMES, type SourceName } from '@trendforge/types'

const DEFAULT_REGION = 'IN'
const LADDER_LIMIT = 20

type Props = {
  searchParams: Promise<{
    region?: string
    limit?: string
    platform?: string
    /** A trend id to open the Desk on, from a library or calendar row. */
    topic?: string
  }>
}

export default async function BoardPage({ searchParams }: Props) {
  const { region = DEFAULT_REGION, limit, platform, topic } = await searchParams
  const activePlatform = asPlatform(platform)
  const openTopic = Number(topic)

  let content
  try {
    const [regions, board, brands, platforms] = await Promise.all([
      fetchRegions(),
      // A link that names a topic asks for the deepest board the API will
      // serve: a week-old item can be well below the default twenty rows,
      // and arriving at rank 1 instead of the item you clicked reads as the
      // link being broken.
      fetchTrends(region, Number.isFinite(openTopic) ? 100 : clampLimit(limit), activePlatform),
      fetchBrands(),
      fetchPlatforms(),
    ])
    content = (
      <Board
        regions={regions}
        board={board}
        brands={brands}
        platforms={platforms}
        activePlatform={activePlatform}
        openTrendId={Number.isFinite(openTopic) ? openTopic : undefined}
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
              Checked <Code>{process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'}</Code>.
            </>
          }
        />
      </div>
    )
  }

  return content
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
