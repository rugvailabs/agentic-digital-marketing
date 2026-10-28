'use client'

import type { StateHeat } from '@trendforge/types'
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'

import { cx } from '@/components/house'
import { INDIA_STATES, INDIA_VIEWBOX } from '@/lib/india-map'

/**
 * India, coloured by where topics are climbing today.
 *
 * The metric is the share of a board's topics that are rising, not the
 * count and not the search volume. Both of those were tried against the
 * real table: counts are near-identical everywhere because the ingest
 * takes the same depth on every board, and volume is a population map —
 * Uttar Pradesh wins every day and the page tells you nothing you did not
 * know before opening it. Share moves between 0 and about 0.4 and the
 * leader changes daily.
 *
 * Clicking a state opens its board, which is the whole reason the map is
 * here rather than a table: it is the fastest way to get from "something
 * is happening somewhere" to the ladder that says what.
 */

/**
 * Five buckets, cut at quantiles rather than at even slices of the range.
 *
 * A linear ramp was the first version and the map came out almost uniformly
 * red: today's shares run 0 to 0.39 with two thirds of the states between
 * 0.07 and 0.25, so a linear scale spends most of its range on a handful of
 * outliers and gives the crowded middle three indistinguishable shades.
 * Quantiles put the same number of states in each step, which is what a
 * choropleth is for — the question is "is my state busier than most", not
 * "what is my state's exact fraction".
 */
const BUCKETS = 5

export function HeatMap({ heat }: { heat: StateHeat[] }) {
  const router = useRouter()
  const [hovered, setHovered] = useState<string | null>(null)

  const byCode = useMemo(() => new Map(heat.map((s) => [s.region_code, s])), [heat])

  // The cut points, recomputed from whatever today looks like. A fixed
  // scale leaves the whole map at the pale end on a quiet day, which reads
  // as "no data" rather than as "a quiet day".
  const cuts = useMemo(() => quantiles(heat.map((s) => s.share)), [heat])
  const peak = useMemo(() => Math.max(...heat.map((s) => s.share), 0), [heat])

  const active = hovered ? byCode.get(hovered) : null

  return (
    <div className="relative">
      <svg
        viewBox={INDIA_VIEWBOX}
        role="img"
        aria-label="Trend heat across India by state"
        className="h-auto w-full"
      >
        {INDIA_STATES.map((state) => {
          const data = byCode.get(state.code)
          const bucket = data ? bucketOf(data.share, cuts) : -1
          const isHovered = hovered === state.code
          return (
            <path
              key={state.code}
              d={state.d}
              role="button"
              tabIndex={data ? 0 : -1}
              aria-label={
                data
                  ? `${data.region_name}: ${data.rising} of ${data.topics} topics rising`
                  : state.name
              }
              onMouseEnter={() => setHovered(state.code)}
              onMouseLeave={() => setHovered((c) => (c === state.code ? null : c))}
              onFocus={() => setHovered(state.code)}
              onBlur={() => setHovered((c) => (c === state.code ? null : c))}
              onClick={() => data && router.push(`/board?region=${state.code}`)}
              onKeyDown={(event) => {
                if (data && (event.key === 'Enter' || event.key === ' ')) {
                  event.preventDefault()
                  router.push(`/board?region=${state.code}`)
                }
              }}
              className={cx(
                'transition-[fill,stroke] duration-150',
                data ? 'cursor-pointer' : 'cursor-default',
              )}
              style={{
                fill: fillFor(bucket),
                stroke: isHovered ? 'var(--color-ink)' : 'var(--color-page)',
                strokeWidth: isHovered ? 2.5 : 1.5,
                strokeLinejoin: 'round',
              }}
            />
          )
        })}
      </svg>

      {/*
       * The readout sits above the map rather than following the pointer.
       * A tooltip chasing the cursor across 36 small shapes flickers, and
       * on a touch screen there is no pointer to chase — tapping a state
       * navigates, and this is what tells you where you are about to go.
       */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center">
        <p
          aria-live="polite"
          className={cx(
            'rounded-sm border border-border bg-overlay px-2.5 py-1 text-xs shadow-card',
            'transition-opacity duration-150',
            active ? 'opacity-100' : 'opacity-0',
          )}
        >
          {active ? (
            <>
              <span className="text-ink">{active.region_name}</span>
              <span className="num ml-2 text-slate">
                {active.rising} of {active.topics} rising
              </span>
            </>
          ) : (
            // Rendered empty rather than removed, so the map does not jump
            // by the height of a tooltip every time the pointer enters.
            <span>&nbsp;</span>
          )}
        </p>
      </div>

      <Legend peak={peak} />
    </div>
  )
}

/**
 * The four interior cut points of five equal-sized buckets.
 *
 * Ties are left alone rather than nudged apart: when a third of the states
 * share a value of exactly 0 they all belong in the coldest bucket, and
 * splitting them across two would be inventing a difference.
 */
export function quantiles(values: number[]): number[] {
  const sorted = [...values].sort((a, b) => a - b)
  if (sorted.length === 0) return [0, 0, 0, 0]
  return Array.from(
    { length: BUCKETS - 1 },
    (_, i) => sorted[Math.floor(((i + 1) * sorted.length) / BUCKETS)] ?? sorted[sorted.length - 1]!,
  )
}

export function bucketOf(share: number, cuts: number[]): number {
  let bucket = 0
  for (const cut of cuts) {
    if (share >= cut) bucket += 1
  }
  return Math.min(bucket, BUCKETS - 1)
}

/**
 * Five steps of one accent, read from CSS rather than computed.
 *
 * The ramp runs the other way up in the light theme — pale recedes on
 * white, dark recedes on near-black — and a component should not know
 * which theme it is in. The tokens do.
 *
 * A state with no board at all is drawn in the card surface: present,
 * outlined, and visibly not part of the data rather than merely cold.
 */
function fillFor(bucket: number): string {
  if (bucket < 0) return 'var(--color-card)'
  return `var(--color-heat-${Math.max(0, Math.min(BUCKETS - 1, bucket))})`
}

function Legend({ peak }: { peak: number }) {
  return (
    <div className="mt-2 flex items-center justify-end gap-2">
      <span className="text-xs text-faint">Quiet</span>
      <span className="flex">
        {Array.from({ length: BUCKETS }, (_, i) => (
          <span
            key={i}
            aria-hidden="true"
            className="block h-2.5 w-6 first:rounded-l-sm last:rounded-r-sm"
            style={{ backgroundColor: fillFor(i) }}
          />
        ))}
      </span>
      <span className="num text-xs text-faint">{Math.round(peak * 100)}% rising</span>
    </div>
  )
}
