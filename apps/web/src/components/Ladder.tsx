'use client'

import type { Trend } from '@trendforge/types'
import { SOURCE_LABELS, type SourceName } from '@trendforge/types'
import { useEffect, useRef, useState } from 'react'

import { Sparkline } from '@/components/Sparkline'
import { Chip, cx } from '@/components/primitives'
import { formatCompactVolume } from '@/lib/format'

/** Whole-list load-in budget is 240ms, so the stagger shrinks as rows grow. */
const SETTLE_BUDGET_MS = 240

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
  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={tabIndex}
      onClick={onSelect}
      className={cx(
        'rule-dotted group grid cursor-pointer grid-cols-[3.25rem_1fr_auto] items-start gap-x-3 py-3 pr-4 pl-1 transition-colors',
        animate ? 'row-settle' : '',
        selected ? 'bg-row-active' : 'hover:bg-row-hover',
      )}
      style={animate ? { animationDelay: `${delayMs}ms` } : undefined}
    >
      {/*
        The rank numeral hangs into the gutter, partly outside the text column —
        a newspaper folio. -ml-1 plus a narrower column than the glyph is what
        produces the overhang; it is not a nudge.
      */}
      <span
        aria-hidden
        className={cx(
          'rank-numeral -ml-1 text-rank select-none',
          selected ? 'text-chilli' : 'text-ink/15 group-hover:text-ink/30',
        )}
      >
        {trend.rank}
      </span>

      <div className="min-w-0 pt-2.5">
        <p className="truncate text-base leading-snug text-ink" title={trend.topic}>
          <span className="sr-only">Rank {trend.rank}: </span>
          {trend.topic}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {trend.category ? <Chip>{trend.category}</Chip> : null}
          {trend.sources.map((source) => (
            <Chip key={source} tone="accent">
              {SOURCE_LABELS[source as SourceName] ?? source}
            </Chip>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3 pt-3.5">
        <Sparkline series={trend.velocity} />
        <span className="num w-14 text-right text-sm text-slate">
          {formatCompactVolume(trend.volume)}
        </span>
      </div>
    </div>
  )
}
