/**
 * The ladder's sparkline, drawn large.
 *
 * Same six points and the same shape as apps/web/src/components/Sparkline.tsx,
 * so a reel closes on the chart the marketer was looking at when they picked
 * the topic. Chilli, because this is velocity and velocity is the one thing
 * that colour means.
 */

import { colours } from '../theme'

export function Sparkline({
  series,
  width,
  height,
  stroke,
  progress,
}: {
  series: number[]
  width: number
  height: number
  stroke: number
  /** 0..1. The line draws itself in rather than appearing whole. */
  progress: number
}) {
  if (series.length < 2) return null

  const high = Math.max(...series)
  const low = Math.min(...series)
  const span = high - low || 1
  const inset = stroke / 2

  const points = series.map((value, index) => {
    const x = inset + (index / (series.length - 1)) * (width - stroke)
    // Inverted: a higher score is nearer the top.
    const y = inset + (1 - (value - low) / span) * (height - stroke)
    return [x, y] as const
  })

  const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x} ${y}`).join(' ')
  // Dash the whole length and offset it, so the stroke is revealed left to
  // right. A clip rectangle would cut the round cap mid-join.
  const length = points.reduce((total, [x, y], i) => {
    const previous = points[i - 1]
    if (!previous) return total
    return total + Math.hypot(x - previous[0], y - previous[1])
  }, 0)

  const last = points[points.length - 1]

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
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
      {last && progress > 0.9 ? (
        <circle cx={last[0]} cy={last[1]} r={stroke * 1.1} fill={colours.chilli} />
      ) : null}
    </svg>
  )
}
