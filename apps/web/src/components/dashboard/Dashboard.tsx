import type { Dashboard as DashboardData, Mover, ProviderBar } from '@trendforge/types'
import { ArrowUpRight, CircleAlert, Film, Image as ImageIcon } from 'lucide-react'
import Link from 'next/link'

import { HeatMap } from '@/components/dashboard/HeatMap'
import { Sparkline } from '@/components/Sparkline'
import { EmptyState } from '@/components/Empty'
import { Card, Panel, SectionLabel, cx } from '@/components/house'
import { formatAge, formatCompactVolume, formatIstDateTime, formatIstTime } from '@/lib/format'

/**
 * The home page.
 *
 * Deliberately not a row of stat tiles — CLAUDE.md rules those out, and
 * they would be the wrong shape anyway: four identical boxes with four
 * numbers in them say that the four numbers are equally important, and
 * here they are not. The map is the page. Everything else is a column
 * beside it, in the order a morning actually goes: where is it hot, what
 * is moving, what did we make, what goes out next, and is anything broken.
 */

export function Dashboard({ data }: { data: DashboardData }) {
  return (
    <div className="mx-auto max-w-[1400px] px-5 py-6">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h1 className="font-display text-xl font-bold text-ink">Today</h1>
        <p className="text-sm text-slate">
          {data.pipeline.last_ingest_at
            ? `Board last updated ${formatAge(data.pipeline.last_ingest_at)}`
            : 'The board has not been ingested yet'}
        </p>
      </header>

      <div className="desk:grid-cols-[minmax(0,5fr)_minmax(0,4fr)] mt-5 grid gap-5">
        <Panel className="p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
            <SectionLabel>Where topics are climbing</SectionLabel>
            <p className="text-xs text-faint">Share of each board that is rising. Click a state.</p>
          </div>
          <div className="mt-3">
            <HeatMap heat={data.heat} />
          </div>
        </Panel>

        <div className="flex min-w-0 flex-col gap-5">
          <Movers movers={data.movers} />
          <Scheduled items={data.scheduled} />
        </div>
      </div>

      <div className="desk:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] mt-5 grid gap-5">
        <Week week={data.week} />
        <div className="flex min-w-0 flex-col gap-5">
          <Budget bars={data.budget} />
          <Pipeline pipeline={data.pipeline} />
        </div>
      </div>
    </div>
  )
}

function Movers({ movers }: { movers: Mover[] }) {
  return (
    <Panel className="p-4">
      <SectionLabel>Moving fastest</SectionLabel>
      {movers.length === 0 ? (
        <div className="mt-3">
          <EmptyState
            art="map"
            title="Nothing is climbing right now."
            hint="Every board is flat or cooling. The next ingest cycle may change that."
          />
        </div>
      ) : (
        <ol className="mt-2">
          {movers.map((mover) => (
            <li key={mover.trend_id} className="border-b border-dotted border-rule last:border-b-0">
              <Link
                href={`/board?region=${mover.region_code}&topic=${mover.trend_id}`}
                className="group flex items-center gap-3 py-2.5 transition-colors duration-150"
              >
                <span className="num w-12 shrink-0 text-right text-sm text-chilli">
                  +{Math.round(mover.delta * 100)}%
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink group-hover:underline group-hover:underline-offset-2">
                    {mover.topic}
                  </span>
                  <span className="block truncate text-xs text-faint">
                    {mover.region_name}, rank {mover.rank}
                  </span>
                </span>
                <span className="shrink-0">
                  <Sparkline series={mover.velocity} />
                </span>
                <span className="num w-12 shrink-0 text-right text-xs text-slate">
                  {formatCompactVolume(mover.volume)}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}

function Scheduled({ items }: { items: DashboardData['scheduled'] }) {
  return (
    <Panel className="p-4">
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel>Going out next</SectionLabel>
        <Link href="/calendar" className="text-xs text-slate hover:text-ink">
          Calendar
        </Link>
      </div>
      {items.length === 0 ? (
        <div className="mt-3">
          <EmptyState
            art="calendar"
            title="Nothing is scheduled."
            hint={
              <>
                Approve something in the{' '}
                <Link href="/library" className="text-ink underline underline-offset-2">
                  library
                </Link>{' '}
                and give it a time.
              </>
            }
          />
        </div>
      ) : (
        <ul className="mt-2 flex flex-col gap-1.5">
          {items.map((item) => (
            <li key={item.job_id}>
              <Link
                href={`/calendar`}
                className="flex items-center gap-2.5 rounded-sm border border-transparent px-1.5 py-1.5 transition-[background-color,border-color] duration-150 hover:border-border hover:bg-row-hover"
              >
                <Poster url={item.preview_url} kind={item.kind} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink">{item.title}</span>
                  <span className="block truncate text-xs text-faint">{item.brand_name}</span>
                </span>
                <span className="num shrink-0 text-right text-xs text-slate">
                  {formatIstDateTime(item.scheduled_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function Week({ week }: { week: DashboardData['week'] }) {
  return (
    <Panel className="p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <SectionLabel>Made this week</SectionLabel>
        <p className="flex items-center gap-4 text-xs text-slate">
          <span className="flex items-center gap-1.5">
            <ImageIcon aria-hidden="true" className="size-3.5" strokeWidth={2} />
            <span className="num text-ink">{week.posts}</span> posts
          </span>
          <span className="flex items-center gap-1.5">
            <Film aria-hidden="true" className="size-3.5" strokeWidth={2} />
            <span className="num text-ink">{week.reels}</span> reels
          </span>
          <Link href="/library" className="hover:text-ink">
            Library
          </Link>
        </p>
      </div>

      {week.items.length === 0 ? (
        <div className="mt-3">
          <EmptyState
            art="grid"
            title="Nothing generated in the last seven days."
            hint={
              <>
                Open a topic on the{' '}
                <Link href="/board" className="text-ink underline underline-offset-2">
                  board
                </Link>{' '}
                and generate a post.
              </>
            }
          />
        </div>
      ) : (
        <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {week.items.map((item) => (
            <li key={item.job_id}>
              <Card interactive className="overflow-hidden">
                <Link href={`/board?region=${item.region_code}&topic=${item.job_id}`}>
                  <Poster url={item.preview_url} kind={item.kind} size="lg" />
                  <span className="block p-2">
                    <span className="line-clamp-2 block text-xs text-ink">{item.title}</span>
                    <span className="mt-1 block truncate text-xs text-faint">
                      {formatAge(item.created_at)}
                    </span>
                  </span>
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

/**
 * A poster, or an honest blank.
 *
 * Always a still — a reel's own URL is an mp4 and a <video> draws nothing
 * until it has fetched a frame, so a grid of reels renders as a column of
 * empty boxes. The renderer saves a poster beside every video.
 */
function Poster({ url, kind, size }: { url: string | null; kind: string; size: 'sm' | 'lg' }) {
  const box = size === 'sm' ? 'size-9 rounded-sm' : 'aspect-square w-full'
  if (!url) {
    return (
      <span
        className={cx(
          'flex shrink-0 items-center justify-center border-border bg-page text-faint',
          size === 'sm' ? 'size-9 shrink-0 rounded-sm border' : 'aspect-square w-full border-b',
        )}
      >
        {kind === 'reel' ? (
          <Film aria-hidden="true" className="size-4" strokeWidth={2} />
        ) : (
          <ImageIcon aria-hidden="true" className="size-4" strokeWidth={2} />
        )}
      </span>
    )
  }
  return (
    /* A MinIO URL on a published port, which next/image cannot be
       configured for without pinning the dev host into next.config. */
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt=""
      loading="lazy"
      className={cx('shrink-0 object-cover', box, size === 'sm' && 'border border-border')}
    />
  )
}

/**
 * What is left to spend today, per provider.
 *
 * Bars because the question is proportional — "can I generate ten posts
 * right now" is about the fraction left, not the integer — and because
 * three numbers in a row would be three stat tiles by another name.
 */
function Budget({ bars }: { bars: ProviderBar[] }) {
  const metered = bars.filter((b) => b.configured)

  return (
    <Panel className="p-4">
      <SectionLabel>Model budget today</SectionLabel>
      {metered.length === 0 ? (
        <div className="mt-3">
          <EmptyState
            art="plug"
            title="No model provider is configured."
            hint="Nothing can be written until one is. Settings lists the variables."
          />
        </div>
      ) : (
        <ul className="mt-3 flex flex-col gap-3">
          {metered.map((bar) => (
            <li key={bar.name}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm text-ink capitalize">{bar.name}</span>
                <span className="num text-xs text-slate">{describe(bar)}</span>
              </div>
              <Bar bar={bar} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function describe(bar: ProviderBar): string {
  if (bar.limit !== null && bar.remaining_today !== null) {
    return `${bar.remaining_today} of ${bar.limit} calls left`
  }
  if (bar.remaining_usd !== null && bar.remaining_usd !== undefined) {
    return `$${bar.remaining_usd.toFixed(2)} left`
  }
  // Configured, reachable, and not metered in a way we can draw. Saying so
  // beats drawing an empty bar that reads as "nothing left".
  return 'no daily limit'
}

function Bar({ bar }: { bar: ProviderBar }) {
  if (bar.limit === null || bar.limit === 0 || bar.remaining_today === null) {
    return (
      <div className="mt-1.5 h-1.5 rounded-full bg-page">
        <div className="h-full w-full rounded-full bg-border" />
      </div>
    )
  }

  const left = Math.max(0, Math.min(1, bar.remaining_today / bar.limit))
  const reserved =
    bar.reserved_for_desk !== null && bar.reserved_for_desk !== undefined
      ? Math.min(1, bar.reserved_for_desk / bar.limit)
      : 0

  return (
    <div className="relative mt-1.5 h-1.5 overflow-hidden rounded-full bg-page">
      <div
        className="h-full rounded-full transition-[width] duration-150"
        style={{
          width: `${left * 100}%`,
          // Chilli only when it is nearly gone. A bar that is always the
          // accent colour is decoration; one that turns at 15% is a signal.
          backgroundColor: left < 0.15 ? 'var(--color-chilli)' : 'var(--color-ink)',
        }}
      />
      {reserved > 0 ? (
        <span
          aria-hidden="true"
          title="Held back for Desk actions"
          className="absolute inset-y-0 w-px bg-turmeric"
          style={{ left: `${reserved * 100}%` }}
        />
      ) : null}
    </div>
  )
}

function Pipeline({ pipeline }: { pipeline: DashboardData['pipeline'] }) {
  const sources = pipeline.sources_configured.length

  return (
    <Panel className="p-4">
      <SectionLabel>Pipeline</SectionLabel>
      <dl className="mt-3 flex flex-col gap-2 text-sm">
        <Row
          label="Database"
          value={pipeline.database ? 'Connected' : 'Unreachable'}
          bad={!pipeline.database}
        />
        <Row label="Topics on the board" value={<span className="num">{pipeline.trends}</span>} />
        <Row label="Regions" value={<span className="num">{pipeline.regions}</span>} />
        <Row
          label="Sources connected"
          value={
            <Link href="/settings" className="hover:underline hover:underline-offset-2">
              <span className="num">{sources}</span>
            </Link>
          }
        />
        <Row
          label="Last ingest"
          value={
            pipeline.last_ingest_at ? formatIstTime(pipeline.last_ingest_at) + ' IST' : 'Never'
          }
          bad={!pipeline.last_ingest_at}
        />
      </dl>

      {pipeline.failed_today > 0 ? (
        <Link
          href="/library?status=draft"
          className="mt-3 flex items-center gap-2 rounded-sm border border-chilli/40 px-2.5 py-2 text-sm text-chilli transition-colors duration-150 hover:bg-chilli/10"
        >
          <CircleAlert aria-hidden="true" className="size-4 shrink-0" strokeWidth={2} />
          <span>
            <span className="num">{pipeline.failed_today}</span>{' '}
            {pipeline.failed_today === 1 ? 'job' : 'jobs'} failed today
          </span>
          <ArrowUpRight aria-hidden="true" className="ml-auto size-4 shrink-0" strokeWidth={2} />
        </Link>
      ) : null}
    </Panel>
  )
}

function Row({
  label,
  value,
  bad = false,
}: {
  label: string
  value: React.ReactNode
  bad?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-dotted border-rule pb-2 last:border-b-0 last:pb-0">
      <dt className="text-slate">{label}</dt>
      <dd className={bad ? 'text-chilli' : 'text-ink'}>{value}</dd>
    </div>
  )
}
