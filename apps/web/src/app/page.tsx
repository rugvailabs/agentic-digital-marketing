import { Board } from '@/components/Board'
import { TopBar } from '@/components/TopBar'
import { Code, Empty } from '@/components/primitives'
import { ApiUnavailable, fetchBrands, fetchHealth, fetchRegions, fetchTrends } from '@/lib/api'

const DEFAULT_REGION = 'IN'
const LADDER_LIMIT = 20

type Props = {
  searchParams: Promise<{ region?: string; limit?: string }>
}

export default async function BoardPage({ searchParams }: Props) {
  const { region = DEFAULT_REGION, limit } = await searchParams
  const health = await fetchHealth()

  let content
  let regionName: string | undefined
  try {
    const [regions, board, brands] = await Promise.all([
      fetchRegions(),
      fetchTrends(region, clampLimit(limit)),
      fetchBrands(),
    ])
    regionName = board.region.name
    content = <Board regions={regions} board={board} brands={brands} />
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
