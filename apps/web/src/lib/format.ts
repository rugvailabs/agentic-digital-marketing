/**
 * en-IN formatting. The product is Indian: lakh/crore grouping, IST clock,
 * Indian date order. Nothing here uses the browser locale, which on a
 * marketer's machine is as likely to be en-US and would silently render
 * 200,000 instead of 2,00,000.
 */

export const LOCALE = 'en-IN'
export const TIME_ZONE = 'Asia/Kolkata'

const full = new Intl.NumberFormat(LOCALE)

/** 200000 -> "2,00,000" (Indian grouping, not thousands). */
export function formatNumber(value: number): string {
  return full.format(value)
}

/**
 * Ladder-width volume: 2.0L / 1.2Cr. Compacting is deliberate — the ladder
 * compares magnitudes at a glance and the Desk shows the exact figure.
 */
export function formatCompactVolume(value: number): string {
  if (!value) return '—'
  if (value >= 10_000_000) return `${trim(value / 10_000_000)}Cr`
  if (value >= 100_000) return `${trim(value / 100_000)}L`
  if (value >= 1_000) return `${trim(value / 1_000)}K`
  return full.format(value)
}

function trim(n: number): string {
  // 2 -> "2", 2.5 -> "2.5": no trailing ".0" cluttering the column.
  return n.toFixed(1).replace(/\.0$/, '')
}

const istTime = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const istDateTime = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** "14:32" in IST, whatever the viewer's machine is set to. */
export function formatIstTime(value: Date | string): string {
  return istTime.format(typeof value === 'string' ? new Date(value) : value)
}

/** "23 Oct, 14:32" in IST. */
export function formatIstDateTime(value: Date | string): string {
  return istDateTime.format(typeof value === 'string' ? new Date(value) : value)
}

export type VelocityTrend = 'rising' | 'settled' | 'cooling'

/**
 * Derived from the series rather than stored: the last point against the mean
 * of the previous five. ±10% is the dead band — without it, every row flickers
 * between rising and cooling on rank noise.
 */
export function velocityTrend(series: readonly number[]): VelocityTrend {
  if (series.length < 2) return 'settled'
  const history = series.slice(0, -1)
  const last = series[series.length - 1] ?? 0
  const seen = history.filter((v) => v > 0)
  if (seen.length === 0) return last > 0 ? 'rising' : 'settled'

  const mean = seen.reduce((a, b) => a + b, 0) / seen.length
  if (mean === 0) return last > 0 ? 'rising' : 'settled'
  const delta = (last - mean) / mean
  if (delta > 0.1) return 'rising'
  if (delta < -0.1) return 'cooling'
  return 'settled'
}

export const TREND_COLOR: Record<VelocityTrend, string> = {
  rising: 'var(--color-chilli)',
  settled: 'var(--color-neem)',
  cooling: 'var(--color-turmeric)',
}

export const TREND_LABEL: Record<VelocityTrend, string> = {
  rising: 'Rising',
  settled: 'Settled',
  cooling: 'Cooling',
}
