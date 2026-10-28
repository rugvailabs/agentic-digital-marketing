'use client'

import type { Brand, Platform, Trend, TrendsResponse } from '@trendforge/types'
import { SOURCE_LABELS, type SourceName } from '@trendforge/types'
import { useEffect, useState } from 'react'

import { Hashtags } from '@/components/Hashtags'
import { Sparkline } from '@/components/Sparkline'
import { Studio } from '@/components/Studio'
import { DeskRail } from '@/components/desk/DeskRail'
import { EmptyState } from '@/components/Empty'
import { MetaCell, SectionLabel, Tabs } from '@/components/house'
import { formatCompactVolume, formatIstDateTime, formatNumber, velocity } from '@/lib/format'

/**
 * The right-hand Desk: one topic, four faces of it.
 *
 * It was a single scroll — facts, then hashtags, then evidence, then the
 * post studio, then the reel panel — and by the time there were two
 * generators on it the page was long enough that the reel controls were
 * below the fold on a laptop. Tabs because these are four different jobs
 * done at four different moments, not four parts of one reading.
 *
 * The header stays above the tabs: which topic you are on is not one of
 * the four things, it is the thing all four are about.
 *
 * Everything is held to a 760px measure and left-aligned. Wider and the
 * eye loses the start of the next line; centred and it stops being a desk.
 */

type Tab = 'overview' | 'post' | 'reel' | 'evidence'

export function Desk({
  region,
  trend,
  brands,
  platforms,
  openOn,
}: {
  region: TrendsResponse['region']
  trend: Trend | null
  brands: Brand[]
  /** Every platform, so a configured one with no row can explain itself. */
  platforms: Platform[]
  /** A tab the ladder has asked for, with a nonce so repeats register. */
  openOn?: { tab: 'post'; nonce: number } | null
}) {
  const [tab, setTab] = useState<Tab>('overview')

  /*
   * A row's "Generate" asks for the Post tab. Keyed on the nonce, not on
   * the tab name, because asking twice for the same tab is a real request
   * — the second press after wandering off to Evidence has to work.
   */
  useEffect(() => {
    if (openOn) setTab(openOn.tab)
  }, [openOn])

  // Back to Overview when the topic changes. Staying on Reel while the
  // subject underneath changes is how you render a video for the wrong
  // story — the tab is about this topic, so it resets with it.
  useEffect(() => {
    setTab('overview')
  }, [trend?.id])

  if (!trend) {
    return (
      <section className="p-6">
        <EmptyState
          art="ladder"
          title={`Nothing selected for ${region.name}.`}
          hint="Pick a topic from the ladder to see its sources and start a post."
        />
      </section>
    )
  }

  return (
    /*
     * Two columns: the reading column takes what is left and the assets
     * rail sits beside it. No max measure on the Desk as a whole any more —
     * at 1440 a 760px cap left four hundred pixels of empty page beside
     * the only thing on screen. The prose inside still has one; a 900px
     * line of body text is unreadable, but that is a rule about a
     * paragraph, not about a panel.
     *
     * The rail is 420px where there is room and shrinks to 280 where
     * there is not, rather than being a fixed width that drops out. 1440
     * minus a 240px sidebar minus the 440px wire leaves the Desk 760, and
     * 480 + 420 is 900 — so a fixed rail disappeared below the fold at
     * exactly the width this product is designed for, and reappeared only
     * when the sidebar was railed. At 280 the rail shows one card per row
     * instead of two, which is a rail of posters rather than a grid of
     * them — still the assets, still beside the writing.
     *
     * A container query, not a viewport one: what decides this is how wide
     * the Desk is, and that changes when the sidebar collapses without the
     * window changing at all.
     */
    <section
      key={`${region.code}-${trend.id}`}
      className="desk-in @min-[46rem]:grid-cols-[minmax(var(--spacing-desk-content),1fr)_minmax(var(--spacing-desk-rail-min),var(--spacing-desk-rail))] grid min-h-full grid-cols-1 items-start"
    >
      <div className="flex min-w-0 flex-col">
        <header className="px-6 pt-6">
          <p className="text-xs text-slate">
            {region.name}, rank {trend.rank}
          </p>
          <h1 className="mt-1.5 font-display text-2xl leading-[1.05] font-bold text-ink">
            {trend.topic}
          </h1>
          {trend.why_trending ? (
            // Under the title, before anything else: it is the one line that
            // says why this is on the board at all, and a marketer reads it
            // before deciding whether to write anything.
            <p className="mt-2 max-w-prose text-sm text-slate">{trend.why_trending}</p>
          ) : null}
        </header>

        <Tabs
          label="Topic"
          value={tab}
          onChange={setTab}
          className="mt-5 px-6"
          tabs={[
            { value: 'overview', label: 'Overview' },
            { value: 'post', label: 'Post' },
            { value: 'reel', label: 'Reel' },
            { value: 'evidence', label: 'Evidence', count: trend.evidence.length },
          ]}
        />

        {/*
         * Keyed by tab so the fade runs again on every change. Without the
         * key React reuses the element, the animation never restarts, and
         * only the first tab you open fades.
         */}
        <div key={tab} role="tabpanel" className="tab-in p-6">
          {tab === 'overview' ? <Overview trend={trend} platforms={platforms} /> : null}
          {tab === 'post' ? <Studio trend={trend} brands={brands} kind="post" /> : null}
          {tab === 'reel' ? <Studio trend={trend} brands={brands} kind="reel" /> : null}
          {tab === 'evidence' ? <Evidence trend={trend} /> : null}
        </div>
      </div>

      <DeskRail trendId={trend.id} />
    </section>
  )
}

function Overview({ trend, platforms }: { trend: Trend; platforms: Platform[] }) {
  const { label: direction } = velocity(trend.velocity)
  // Same rule as the ladder: no volume means no series, so there is no
  // direction to report and no colour that would mean anything.
  const hasSeries = trend.volume > 0

  return (
    <div className="flex flex-col gap-6">
      {/*
        One line of facts, divided by hairlines rather than laid out on a
        grid: four grid cells read as four separate things, where this is a
        single reading of one topic. It wraps only when the measure runs out.
      */}
      <div className="desk:flex desk:flex-wrap desk:items-start desk:gap-x-0 desk:gap-y-4 grid grid-cols-2 gap-x-6 gap-y-3 border-y border-border py-3">
        <MetaCell label="Volume" numeric>
          {trend.volume ? formatNumber(trend.volume) : '—'}
        </MetaCell>
        <MetaCell label="Velocity">
          {hasSeries ? (
            <span className="flex items-center gap-2">
              <Sparkline series={trend.velocity} width={56} height={14} />
              {direction}
            </span>
          ) : (
            <span className="text-slate">Not tracked</span>
          )}
        </MetaCell>
        <MetaCell label="Category">{trend.category ?? '—'}</MetaCell>
        {/*
          No Sources cell: a fifth value wraps the row onto a second line,
          and the sources are named against each row of the evidence tab,
          which is where you go to act on them.
        */}
        <MetaCell label="Updated" numeric>
          {formatIstDateTime(trend.updated_at)} IST
        </MetaCell>
      </div>

      <Hashtags trend={trend} platforms={platforms} />
    </div>
  )
}

function Evidence({ trend }: { trend: Trend }) {
  return (
    <div className="flex flex-col gap-2">
      <SectionLabel>Where this came from</SectionLabel>
      {trend.evidence.length === 0 ? (
        <EmptyState
          art="search"
          title="No links recorded for this topic."
          hint="It was ranked from search volume alone, with no article behind it."
        />
      ) : (
        <ul className="flex flex-col">
          {trend.evidence.map((row, i) => (
            <EvidenceRow key={`${row.source}-${row.rank}-${i}`} row={row} />
          ))}
        </ul>
      )}
    </div>
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
            className="underline decoration-border underline-offset-2 hover:decoration-ink"
          >
            {title}
          </a>
        ) : (
          title
        )}
        {attribution ? <span className="text-slate"> — {attribution}</span> : null}
        {growth !== null ? (
          <span className="num text-slate"> +{formatCompactVolume(growth)}%</span>
        ) : null}
      </span>
    </li>
  )
}
