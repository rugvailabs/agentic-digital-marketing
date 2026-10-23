import type { Trend, TrendsResponse } from '@trendforge/types'
import { SOURCE_LABELS, type SourceName } from '@trendforge/types'

import { Sparkline } from '@/components/Sparkline'
import { Empty, MetaCell, SectionLabel } from '@/components/primitives'
import {
  formatCompactVolume,
  formatIstDateTime,
  formatNumber,
  velocity,
} from '@/lib/format'

/**
 * The right-hand Desk: what the selected topic is, and where the content
 * studio will live in step 2.
 *
 * Everything is held to a 760px measure and left-aligned. Wider than that and
 * the eye loses the start of the next line; centred and it stops being a desk.
 */
export function Desk({
  region,
  trend,
}: {
  region: TrendsResponse['region']
  trend: Trend | null
}) {
  if (!trend) {
    return (
      <section className="max-w-desk p-6">
        <Empty
          title={`Nothing selected for ${region.name}.`}
          hint="Pick a topic from the ladder to see its sources and start a post."
        />
      </section>
    )
  }

  const { label: direction } = velocity(trend.velocity)

  return (
    <section
      key={`${region.code}-${trend.rank}`}
      className="desk-in flex max-w-desk flex-col gap-6 p-6"
    >
      <div>
        <p className="text-xs text-slate">
          {region.name} · rank {trend.rank}
        </p>
        <h1 className="mt-1.5 font-display text-2xl leading-[1.05] font-bold text-ink">
          {trend.topic}
        </h1>
        {trend.hashtags.length > 0 ? (
          <p className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 text-sm font-medium text-ink">
            {trend.hashtags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </p>
        ) : null}
      </div>

      {/*
        One line of facts, divided by hairlines rather than laid out on a grid:
        four grid cells read as four separate things, where this is a single
        reading of one topic. It wraps only when the measure runs out.
      */}
      <div className="desk:flex desk:flex-wrap desk:items-start desk:gap-x-0 desk:gap-y-4 grid grid-cols-2 gap-x-6 gap-y-3 border-y border-rule py-3">
        <MetaCell label="Volume" numeric>
          {trend.volume ? formatNumber(trend.volume) : '—'}
        </MetaCell>
        <MetaCell label="Velocity">
          <span className="flex items-center gap-2">
            <Sparkline series={trend.velocity} width={56} height={14} />
            {direction}
          </span>
        </MetaCell>
        <MetaCell label="Category">{trend.category ?? '—'}</MetaCell>
        {/*
          No Sources cell: a fifth value wraps the row onto a second line, and
          the sources are already named against each row of the evidence list
          below, which is where you go to act on them.
        */}
        <MetaCell label="Updated" numeric>
          {formatIstDateTime(trend.updated_at)} IST
        </MetaCell>
      </div>

      <div className="flex flex-col gap-2">
        <SectionLabel>Evidence</SectionLabel>
        {trend.evidence.length === 0 ? (
          <p className="text-sm text-slate">No links recorded for this topic.</p>
        ) : (
          <ul className="flex flex-col">
            {trend.evidence.slice(0, 8).map((row, i) => (
              <EvidenceRow key={`${row.source}-${row.rank}-${i}`} row={row} />
            ))}
          </ul>
        )}
      </div>

      {/*
        Plain text under a rule, not a card: a bordered box here would claim
        the one visual role reserved for a rendered image or video.
      */}
      <div className="border-t border-rule pt-4">
        <p className="text-sm text-ink">Content studio arrives in step 2.</p>
        <p className="mt-1.5 text-sm text-slate">
          Captions, square images and 9:16 reels will be generated here from this topic, using
          its hashtags and the sources above as the brief.
        </p>
      </div>
    </section>
  )
}

function EvidenceRow({ row }: { row: Record<string, unknown> }) {
  const source = String(row.source ?? '')
  const label = SOURCE_LABELS[source as SourceName] ?? source
  const title = String(row.title ?? '')
  const url = typeof row.url === 'string' ? row.url : null
  const publisher = typeof row.publisher === 'string' ? row.publisher : null
  const channel = typeof row.channel === 'string' ? row.channel : null
  const attribution = publisher ?? channel
  const growth = typeof row.volume_growth_pct === 'number' ? row.volume_growth_pct : null

  return (
    <li className="rule-dotted grid grid-cols-[1.5rem_4.5rem_1fr] items-baseline gap-3 py-2 text-sm">
      <span className="num text-slate">{String(row.rank ?? '')}</span>
      <span className="text-slate">{label}</span>
      <span className="min-w-0 text-ink">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="underline decoration-rule underline-offset-2 hover:decoration-ink"
          >
            {title}
          </a>
        ) : (
          title
        )}
        {attribution ? <span className="text-slate"> — {attribution}</span> : null}
        {growth !== null ? (
          <span className="num text-slate"> · +{formatCompactVolume(growth)}%</span>
        ) : null}
      </span>
    </li>
  )
}
