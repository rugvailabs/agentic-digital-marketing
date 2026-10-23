import { TREND_COLOR, TREND_LABEL, velocityTrend } from '@/lib/format'

type Props = {
  series: readonly number[]
  width?: number
  height?: number
  label?: string
}

/**
 * Six-point velocity line. Hand-drawn SVG rather than a chart library: it is
 * one polyline, and a library would ship axes, tooltips and a legend we spent
 * the design notes explicitly removing.
 */
export function Sparkline({ series, width = 56, height = 18, label }: Props) {
  const trend = velocityTrend(series)
  const color = TREND_COLOR[trend]

  const points = toPoints(series, width, height)
  const description = label ?? `${TREND_LABEL[trend]} — last ${series.length} snapshots`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={description}
      className="shrink-0 overflow-visible"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* The head of the line is the only marked point: it is "now". */}
      <circle cx={lastX(width, series.length)} cy={lastY(series, height)} r={1.75} fill={color} />
    </svg>
  )
}

function scaleY(value: number, max: number, height: number): number {
  const inset = 2
  const usable = height - inset * 2
  return height - inset - (max === 0 ? 0 : (value / max) * usable)
}

function toPoints(series: readonly number[], width: number, height: number): string {
  if (series.length === 0) return ''
  const max = Math.max(...series, 1)
  const step = series.length > 1 ? width / (series.length - 1) : 0
  return series.map((v, i) => `${(i * step).toFixed(2)},${scaleY(v, max, height).toFixed(2)}`).join(' ')
}

function lastX(width: number, count: number): number {
  return count > 1 ? width : width / 2
}

function lastY(series: readonly number[], height: number): number {
  const max = Math.max(...series, 1)
  return scaleY(series[series.length - 1] ?? 0, max, height)
}
