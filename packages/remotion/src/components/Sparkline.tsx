/**
 * The ladder's sparkline.
 *
 * Same six points and the same shape as apps/web/src/components/Sparkline.tsx,
 * so a reel closes on the chart the marketer was looking at when they picked
 * the topic. Chilli, because this is velocity and velocity is the one thing
 * that colour means.
 *
 * Drawn twice in a reel: small in the masthead, where it is a mark saying
 * "this is a trend", and large on the closing card, where it is the subject.
 */

import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'

import { colours } from '../theme'

export function Sparkline({
  series,
  width,
  height,
  stroke,
  progress,
  /** Frame the end dot pops on. Omit for the small masthead mark. */
  dotAt,
}: {
  series: number[]
  width: number
  height: number
  stroke: number
  /** 0..1. The line draws itself in rather than appearing whole. */
  progress: number
  dotAt?: number
}) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()

  if (series.length < 2) return null

  const high = Math.max(...series)
  const low = Math.min(...series)
  const span = high - low || 1
  // Room for the end dot, which is wider than the stroke and would otherwise
  // be clipped by the viewBox on the last point.
  const inset = stroke * 1.6

  const points = series.map((value, index) => {
    const x = inset + (index / (series.length - 1)) * (width - inset * 2)
    // Inverted: a higher score is nearer the top.
    const y = inset + (1 - (value - low) / span) * (height - inset * 2)
    return [x, y] as const
  })

  const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x} ${y}`).join(' ')
  // Dash the whole length and offset it, so the stroke is revealed left to
  // right. A clip rectangle would cut the round cap mid-join.
  const length = points.reduce((total, [x, y], i) => {
    const previous = points[i - 1]
    return previous ? total + Math.hypot(x - previous[0], y - previous[1]) : total
  }, 0)

  const last = points[points.length - 1]
  // Springs where something lands, interpolation where something travels.
  // The dot is the end of the line arriving, so it gets the spring.
  const pop =
    dotAt === undefined
      ? progress > 0.98
        ? 1
        : 0
      : spring({
          frame: frame - dotAt,
          fps,
          config: { damping: 13, stiffness: 220, mass: 0.5 },
          durationInFrames: 12,
        })

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="presentation">
      <path
        d={path}
        fill="none"
        stroke={colours.chilli}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={length}
        strokeDashoffset={length * (1 - progress)}
      />
      {last && pop > 0.01 ? (
        <circle
          cx={last[0]}
          cy={last[1]}
          r={stroke * 1.15 * Math.min(pop, 1.15)}
          fill={colours.chilli}
          opacity={interpolate(pop, [0, 0.3], [0, 1], { extrapolateRight: 'clamp' })}
        />
      ) : null}
    </svg>
  )
}
