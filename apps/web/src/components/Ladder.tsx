'use client'

import type { Trend } from '@trendforge/types'
import { SOURCE_LABELS, SOURCE_MARKS, type SourceName } from '@trendforge/types'
import { useEffect, useRef, useState } from 'react'

import { Sparkline } from '@/components/Sparkline'
import { Chip, cx } from '@/components/house'
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
          position={i + 1}
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
  position,
  selected,
  tabIndex,
  onSelect,
  animate,
  delayMs,
}: {
  trend: Trend
  /**
   * Where this row sits in the list being looked at, counting from 1.
   *
   * Not `trend.rank`, which is the topic's rank on the whole board. With a
   * platform filter on, the board's ranks arrive as 17, 18, 20, 22, 23 — so
   * the ladder opened at seventeen and skipped, which reads as missing
   * rows rather than as a filtered list. The numeral is the folio of the
   * list you are reading; the board rank is a fact about the topic, and it
   * is shown as one below when the two differ.
   */
  position: number
  selected: boolean
  tabIndex: number
  onSelect: () => void
  animate: boolean
  delayMs: number
}) {
  const headline = position <= HEADLINE_RANKS
  // Only worth saying when it is not what the numeral already says.
  const boardRank = trend.rank === position ? null : trend.rank
  // A single source is the norm, so a chip saying so is noise on every row. It
  // earns its place only when corroboration is the interesting fact.
  // Prefer the per-platform rows: they carry that platform's own rank and
  // volume, so a mark can say "2nd on Reddit, 18,400 upvotes" rather than
  // just naming it. `sources` is the fallback for a board whose platform rows
  // have not been synced yet.
  const marks: Array<{ name: SourceName; title: string }> =
    trend.platforms.length > 0
      ? trend.platforms.map((p) => ({
          name: p.platform as SourceName,
          title: platformTitle(p.platform as SourceName, p.rank, p.volume),
        }))
      : trend.sources.map((s) => ({
          name: s as SourceName,
          title: SOURCE_LABELS[s as SourceName] ?? s,
        }))
  // A single platform is the norm, so marks on every row would be noise. They
  // earn their place when corroboration is the interesting fact.
  const corroborated = marks.length > 1
  // News and YouTube report no volume, so a news-only topic has no series to
  // chart. Drawing a sparkline from its score would invent a trend line out of
  // ranking noise, so the row says where it came from instead.
  const hasSeries = trend.volume > 0
  const origin = SOURCE_LABELS[marks[0]?.name as SourceName] ?? marks[0]?.name ?? ''

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
        {position}
      </span>

      <div className={cx('min-w-0', headline ? 'pt-2' : 'pt-0.5')}>
        {/*
          Two lines at 15px rather than one truncated line at 16px: a curated
          headline carries the useful detail at the end ("…in Goa", "…ahead of
          Navy induction"), which is exactly what an ellipsis removed.
        */}
        <p
          className="text-[15px] leading-[1.3] text-ink [display:-webkit-box] [overflow:hidden] [-webkit-box-orient:vertical] [-webkit-line-clamp:2]"
          title={trend.topic}
        >
          <span className="sr-only">
            {boardRank === null
              ? `Rank ${position}: `
              : `${position} of the filtered list, rank ${boardRank} on the board: `}
          </span>
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
          {/*
            The topic's rank on the unfiltered board, shown only when the
            numeral to the left is not already it. Muted and set in the
            number face: it is a reference, not the row's position.
          */}
          {boardRank !== null ? (
            <span className="shrink-0 font-display text-xs whitespace-nowrap text-faint tabular-nums">
              rank {boardRank}
            </span>
          ) : null}
          {corroborated ? (
            // Plain type, not chips. Six bordered boxes would not fit the
            // 420px column, and CLAUDE.md puts hierarchy in type rather than
            // in boxes — a wire desk sets its source codes, it does not
            // frame them.
            <span className="flex shrink-0 items-center gap-1 text-[11px] leading-5 tracking-wide text-slate">
              {marks.map((mark) => (
                <abbr
                  key={mark.name}
                  title={mark.title}
                  className="no-underline"
                  aria-label={mark.title}
                >
                  {SOURCE_MARKS[mark.name] ?? mark.name.slice(0, 2).toUpperCase()}
                </abbr>
              ))}
            </span>
          ) : null}
        </div>
      </div>

      <div className={cx('flex items-center gap-3', headline ? 'pt-3' : 'pt-1')}>
        {hasSeries ? <Sparkline series={trend.velocity} /> : null}
        <span
          className={cx(
            'w-14 text-right text-sm',
            hasSeries ? 'num text-slate' : 'truncate text-slate',
          )}
        >
          {hasSeries ? formatCompactVolume(trend.volume) : origin}
        </span>
      </div>
    </div>
  )
}

/**
 * A mark's tooltip: the platform, its rank there, and what it counted.
 *
 * The number is named rather than shown bare, because it is not comparable
 * across platforms — upvotes on Reddit, views on YouTube, posts on Instagram —
 * and an unlabelled figure invites exactly that comparison.
 */
function platformTitle(name: SourceName, rank: number | null, volume: number): string {
  const label = SOURCE_LABELS[name] ?? name
  const position = rank ? `#${rank} on ${label}` : label
  if (!volume) return position
  const counted: Partial<Record<SourceName, string>> = {
    reddit: 'upvotes',
    youtube: 'views',
    instagram: 'posts',
    google_trends: 'searches',
    x: 'posts',
  }
  const unit = counted[name]
  return unit ? `${position} — ${volume.toLocaleString('en-IN')} ${unit}` : position
}
