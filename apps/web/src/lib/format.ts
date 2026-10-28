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

/**
 * Google Trends category names are written out in full ("Business and
 * Finance", "Travel and Transportation") and do not fit a ladder chip at 420px
 * — they truncated mid-word. The Desk still shows the full name; this is the
 * dense-column label only.
 */
const SHORT_CATEGORY: Record<string, string> = {
  'Autos and Vehicles': 'Autos',
  'Beauty and Fashion': 'Beauty',
  'Business and Finance': 'Business',
  'Food and Drink': 'Food',
  'Hobbies and Leisure': 'Hobbies',
  'Jobs and Education': 'Jobs',
  'Law and Government': 'Law',
  'Pets and Animals': 'Pets',
  'Travel and Transportation': 'Travel',
  Technology: 'Tech',
}

export function shortCategory(category: string): string {
  return SHORT_CATEGORY[category] ?? category
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

/**
 * Colour per direction. Chilli is spent *only* here, on rising — that is what
 * keeps the one accent meaningful everywhere else on the board.
 *
 * Note this departs from the CLAUDE.md palette note, which reads neem as
 * "settled" and turmeric as "watch": here neem marks falling and turmeric is
 * unused. Keep the two in step if the palette note is revised.
 */
export const TREND_COLOR: Record<VelocityTrend, string> = {
  rising: 'var(--color-chilli)',
  settled: 'var(--color-slate)',
  cooling: 'var(--color-neem)',
}

export const TREND_LABEL: Record<VelocityTrend, string> = {
  rising: 'Rising',
  settled: 'Flat',
  cooling: 'Falling',
}

/**
 * The single place a velocity series turns into something you can render.
 * Label and colour are read off one derivation, so the written direction and
 * the line colour cannot disagree.
 */
export function velocity(series: readonly number[]): {
  trend: VelocityTrend
  color: string
  label: string
} {
  const trend = velocityTrend(series)
  return { trend, color: TREND_COLOR[trend], label: TREND_LABEL[trend] }
}

const istDate = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

/** "23 Oct 2026" in IST. */
export function formatIstDate(value: Date | string): string {
  return istDate.format(typeof value === 'string' ? new Date(value) : value)
}

/**
 * "2 hours ago", "yesterday", "23 Oct".
 *
 * Relative only inside a week. Past that, a date is more useful than "14
 * days ago" — nobody counts back from today to find last month's work, and
 * the library sorts newest first so the exact figure is what distinguishes
 * one old item from another.
 */
export function formatAge(value: Date | string, now: Date = new Date()): string {
  const then = typeof value === 'string' ? new Date(value) : value
  const minutes = Math.round((now.getTime() - then.getTime()) / 60_000)

  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`

  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`

  const days = Math.round(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  return formatIstDate(then)
}

/**
 * The IST calendar day a timestamp falls on, as "YYYY-MM-DD".
 *
 * Not `toISOString().slice(0, 10)`, which is the UTC day: at 01:00 IST that
 * is yesterday, so a post scheduled for Monday morning would land on Sunday
 * in the calendar grid. en-CA is used because it formats as ISO.
 */
const istDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

export function istDayKey(value: Date | string): string {
  return istDay.format(typeof value === 'string' ? new Date(value) : value)
}
