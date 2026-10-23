import type { Trend, TrendsResponse } from '@trendforge/types'
import { SOURCE_LABELS, type SourceName } from '@trendforge/types'

import { Sparkline } from '@/components/Sparkline'
import { AssetFrame, Chip, Empty, Field, SectionLabel } from '@/components/primitives'
import {
  TREND_LABEL,
  formatCompactVolume,
  formatIstDateTime,
  formatNumber,
  velocityTrend,
} from '@/lib/format'

/**
 * The right-hand Desk: what the selected topic is, and where the content
 * studio will live in step 2.
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
      <section className="p-6">
        <Empty
          title={`Nothing selected for ${region.name}.`}
          hint="Pick a topic from the ladder to see its sources and start a post."
        />
      </section>
    )
  }

  const trend_ = velocityTrend(trend.velocity)

  return (
    <section key={`${region.code}-${trend.rank}`} className="desk-in flex flex-col gap-6 p-6">
      <div>
        <p className="text-xs text-slate">
          {region.name} · rank {trend.rank}
        </p>
        <h1 className="mt-1 font-display text-xl leading-tight font-bold text-ink">
          {trend.topic}
        </h1>
        {trend.hashtags.length > 0 ? (
          <p className="num mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-chilli">
            {trend.hashtags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </p>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-4 border-t border-rule pt-4 sm:grid-cols-3">
        <Field label="Volume">
          {trend.volume ? formatNumber(trend.volume) : '—'}
        </Field>
        <Field label="Score">{trend.score.toFixed(1)}</Field>
        <Field label="Category">{trend.category ?? '—'}</Field>
        <Field label="Velocity">
          <span className="flex items-center gap-2">
            <Sparkline series={trend.velocity} width={64} height={16} />
            {TREND_LABEL[trend_]}
          </span>
        </Field>
        <Field label="Sources">
          <span className="flex flex-wrap gap-1.5">
            {trend.sources.map((source) => (
              <Chip key={source} tone="accent">
                {SOURCE_LABELS[source as SourceName] ?? source}
              </Chip>
            ))}
          </span>
        </Field>
        <Field label="Updated">{formatIstDateTime(trend.updated_at)} IST</Field>
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

      <AssetFrame>
        <p className="text-sm text-ink">Content studio arrives in step 2.</p>
        <p className="mt-1.5 text-sm text-slate">
          Captions, square images and 9:16 reels will be generated here from this topic, using
          its hashtags and the sources above as the brief.
        </p>
      </AssetFrame>
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
  const views = typeof row.volume_growth_pct === 'number' ? row.volume_growth_pct : null

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
            className="underline decoration-rule underline-offset-2 hover:decoration-chilli"
          >
            {title}
          </a>
        ) : (
          title
        )}
        {attribution ? <span className="text-slate"> — {attribution}</span> : null}
        {views !== null ? (
          <span className="num text-slate"> · +{formatCompactVolume(views)}%</span>
        ) : null}
      </span>
    </li>
  )
}
