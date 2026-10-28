import type { ReactNode } from 'react'

import { cx } from '@/components/house'

/**
 * Empty states, with an illustration drawn here rather than imported.
 *
 * Five small SVGs in the product's own palette: a ladder with no rows, a
 * grid with no cards, a calendar with no items, a map with nothing hot, a
 * plug with nothing in it. They are made of the same shapes the real
 * surface is made of — the ladder's dotted rules, the card's radius, the
 * map's quantile ramp — so an empty page reads as the page it will become
 * rather than as a different screen.
 *
 * No illustration library, and nothing decorative: an empty state's job is
 * to say what to do next, and a picture that does not resemble what is
 * missing is just a picture.
 */

export type EmptyArt = 'ladder' | 'grid' | 'calendar' | 'map' | 'plug' | 'search'

export function EmptyState({
  art,
  title,
  hint,
  action,
  className,
}: {
  art: EmptyArt
  title: string
  /** What to do next. Required in spirit — CLAUDE.md asks every empty
   *  state to say it — and optional only because some callers put it in
   *  the action instead. */
  hint?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cx(
        'flex flex-col items-start gap-3 rounded-md border border-dashed border-border p-6',
        className,
      )}
    >
      <Art art={art} />
      <div>
        <p className="text-sm text-ink">{title}</p>
        {hint ? <p className="mt-1 max-w-prose text-sm text-slate">{hint}</p> : null}
      </div>
      {action}
    </div>
  )
}

/**
 * The drawings.
 *
 * `currentColor` throughout, inherited from a slate wrapper, so every one
 * of them is theme-correct without a single colour literal. The only
 * exception is the one chilli stroke each carries, which is the same
 * accent the real surface spends.
 */
function Art({ art }: { art: EmptyArt }) {
  const common = {
    width: 96,
    height: 60,
    viewBox: '0 0 96 60',
    fill: 'none',
    'aria-hidden': true as const,
    className: 'text-faint',
  }

  if (art === 'ladder') {
    return (
      <svg {...common}>
        {/* Three ladder rows with nothing on them — dotted rules and a
            rank numeral's worth of space at the left, which is what the
            board looks like with the data taken out. */}
        {[12, 28, 44].map((y, i) => (
          <g key={y}>
            <rect
              x="4"
              y={y - 7}
              width="12"
              height="14"
              rx="2"
              fill="currentColor"
              opacity={0.25 - i * 0.06}
            />
            <line
              x1="22"
              y1={y - 3}
              x2={74 - i * 14}
              y2={y - 3}
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              opacity={0.5 - i * 0.12}
            />
            <line
              x1="4"
              y1={y + 9}
              x2="92"
              y2={y + 9}
              stroke="currentColor"
              strokeWidth="1"
              strokeDasharray="2 3"
              opacity="0.4"
            />
          </g>
        ))}
      </svg>
    )
  }

  if (art === 'grid') {
    return (
      <svg {...common}>
        {[0, 1, 2, 3].map((i) => (
          <rect
            key={i}
            x={4 + i * 23}
            y="10"
            width="19"
            height="26"
            rx="3"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray={i === 0 ? undefined : '3 3'}
            opacity={i === 0 ? 0.8 : 0.45}
          />
        ))}
        {/* One card has something in it: the first one you will make. */}
        <rect x="8" y="14" width="11" height="11" rx="2" fill="currentColor" opacity="0.3" />
        <line
          x1="8"
          y1="30"
          x2="19"
          y2="30"
          stroke="var(--color-chilli)"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    )
  }

  if (art === 'calendar') {
    return (
      <svg {...common}>
        <rect
          x="10"
          y="8"
          width="76"
          height="44"
          rx="4"
          stroke="currentColor"
          strokeWidth="1.5"
          opacity="0.6"
        />
        <line
          x1="10"
          y1="20"
          x2="86"
          y2="20"
          stroke="currentColor"
          strokeWidth="1.5"
          opacity="0.6"
        />
        {[0, 1, 2, 3].map((col) =>
          [0, 1].map((row) => (
            <rect
              key={`${col}-${row}`}
              x={18 + col * 17}
              y={27 + row * 13}
              width="11"
              height="7"
              rx="1.5"
              fill="currentColor"
              opacity="0.18"
            />
          )),
        )}
        {/* Today, with nothing on it. */}
        <rect
          x="35"
          y="27"
          width="11"
          height="7"
          rx="1.5"
          fill="var(--color-chilli)"
          opacity="0.5"
        />
      </svg>
    )
  }

  if (art === 'map') {
    return (
      <svg {...common}>
        {/* Not India — a suggestion of a choropleth, in the real ramp.
            A recognisable India here would compete with the actual map
            two hundred pixels away. */}
        {[
          [8, 14, 22, 18, 0.5],
          [32, 10, 26, 22, 0.3],
          [60, 16, 24, 16, 0.65],
          [12, 34, 30, 16, 0.2],
          [46, 34, 20, 18, 0.45],
          [70, 36, 16, 14, 0.15],
        ].map(([x, y, w, h, o], i) => (
          <rect key={i} x={x} y={y} width={w} height={h} rx="3" fill="currentColor" opacity={o} />
        ))}
      </svg>
    )
  }

  if (art === 'search') {
    return (
      <svg {...common}>
        <circle cx="40" cy="26" r="15" stroke="currentColor" strokeWidth="2" opacity="0.6" />
        <line
          x1="51"
          y1="37"
          x2="64"
          y2="50"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.6"
        />
        <line
          x1="33"
          y1="26"
          x2="47"
          y2="26"
          stroke="var(--color-chilli)"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    )
  }

  // plug
  return (
    <svg {...common}>
      <rect
        x="10"
        y="18"
        width="34"
        height="24"
        rx="4"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.7"
      />
      <line x1="44" y1="24" x2="56" y2="24" stroke="currentColor" strokeWidth="2" opacity="0.5" />
      <line x1="44" y1="36" x2="56" y2="36" stroke="currentColor" strokeWidth="2" opacity="0.5" />
      {/* The far end, unconnected. */}
      <rect
        x="64"
        y="18"
        width="22"
        height="24"
        rx="4"
        stroke="var(--color-chilli)"
        strokeWidth="1.5"
        strokeDasharray="3 3"
      />
    </svg>
  )
}
