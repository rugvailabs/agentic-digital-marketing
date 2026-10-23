'use client'

import type { Trend } from '@trendforge/types'
import { SOURCE_LABELS, type SourceName } from '@trendforge/types'
import { useEffect, useRef, useState } from 'react'

import { Sparkline } from '@/components/Sparkline'
import { Chip, cx } from '@/components/primitives'
import { formatCompactVolume, shortCategory } from '@/lib/format'

/** Whole-list load-in budget is 240ms, so the stagger shrinks as rows grow. */
const SETTLE_BUDGET_MS = 240

/**
 * Ranks above this drop to the smaller numeral. The top of the board earns the
 * 64px folio; past third place the rank is reference, not headline.
 */
const HEADLINE_RANKS = 3

export function Ladder({
  trends,
  selectedRank,
  onSelect,
}: {
  trends: Trend[]
  selectedRank: number
  onSelect: (rank: number) => void
}) {
  const listRef = useRef<HTMLDivElement>(null)
  // Animate on first mount only; re-animating on every selection would make the
  // ladder twitch, and the design notes allow exactly one load-in.
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(true), SETTLE_BUDGET_MS + 60)
    return () => clearTimeout(timer)
  }, [])

  const stagger = trends.length > 1 ? Math.min(18, SETTLE_BUDGET_MS / trends.length) : 0
  const index = Math.max(
    0,
    trends.findIndex((t) => t.rank === selectedRank),
  )

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number | 'first' | 'last'> = {
      ArrowDown: 1,
      ArrowUp: -1,
      Home: 'first',
      End: 'last',
    }
    const move = moves[event.key]
    if (move === undefined) return

    event.preventDefault()
    const next =
      move === 'first'
        ? 0
        : move === 'last'
          ? trends.length - 1
          : Math.min(trends.length - 1, Math.max(0, index + move))

    const row = trends[next]
    if (!row) return
    onSelect(row.rank)
    listRef.current?.querySelectorAll<HTMLElement>('[role="option"]')[next]?.focus()
  }

  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label="Trending topics"
      onKeyDown={onKeyDown}
      className="flex flex-col"
    >
      {trends.map((trend, i) => (
        <Row
          key={trend.rank}
          trend={trend}
          selected={trend.rank === selectedRank}
          tabIndex={i === index ? 0 : -1}
          onSelect={() => onSelect(trend.rank)}
          animate={!settled}
          delayMs={i * stagger}
        />
      ))}
    </div>
  )
}

function Row({
  trend,
  selected,
  tabIndex,
  onSelect,
  animate,
  delayMs,
}: {
  trend: Trend
  selected: boolean
  tabIndex: number
  onSelect: () => void
  animate: boolean
  delayMs: number
}) {
  const headline = trend.rank <= HEADLINE_RANKS
  // A single source is the norm, so a chip saying so is noise on every row. It
  // earns its place only when corroboration is the interesting fact.
  const corroborated = trend.sources.length > 1

  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={tabIndex}
      onClick={onSelect}
      className={cx(
        'rule-dotted group grid cursor-pointer grid-cols-[4.5rem_1fr_auto] items-start gap-x-3 py-2 pr-4 pl-1 transition-colors',
        animate ? 'row-settle' : '',
        selected ? 'bg-row-active' : 'hover:bg-row-hover',
      )}
      style={animate ? { animationDelay: `${delayMs}ms` } : undefined}
    >
      {/*
        The rank numeral hangs into the gutter, partly outside the text column —
        a newspaper folio. The negative margin against the row padding is what
        produces the overhang; it is not a nudge. Right-aligned so one- and
        two-digit ranks share an edge. Ink at every rank: the accent belongs to
        rising velocity, and selection is carried by the row ground.
      */}
      <span
        aria-hidden
        className={cx(
          'rank-numeral -ml-2 block text-right text-ink select-none',
          headline ? 'text-rank' : 'text-rank-sm',
        )}
      >
        {trend.rank}
      </span>

      <div className={cx('min-w-0', headline ? 'pt-2' : 'pt-0.5')}>
        <p className="truncate text-base leading-snug text-ink" title={trend.topic}>
          <span className="sr-only">Rank {trend.rank}: </span>
          {trend.topic}
        </p>
        {/*
          No wrapping: a long category would push the chips onto a second line
          and give that row a taller box, breaking the ladder's rhythm.
        */}
        <div className="mt-1 flex items-center gap-1.5 overflow-hidden">
          {trend.category ? (
            // The inner block span is what truncates: text-overflow does not
            // apply to the inline-flex chip itself, so an ellipsis set there
            // never renders and the text runs into the border.
            <Chip className="min-w-0 shrink" title={trend.category}>
              <span className="block truncate">{shortCategory(trend.category)}</span>
            </Chip>
          ) : null}
          {corroborated
            ? trend.sources.map((source) => (
                <Chip key={source}>{SOURCE_LABELS[source as SourceName] ?? source}</Chip>
              ))
            : null}
        </div>
      </div>

      <div className={cx('flex items-center gap-3', headline ? 'pt-3' : 'pt-1')}>
        <Sparkline series={trend.velocity} />
        <span className="num w-14 text-right text-sm text-slate">
          {formatCompactVolume(trend.volume)}
        </span>
      </div>
    </div>
  )
}
