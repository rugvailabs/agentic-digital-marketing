import { TIME_ZONE, istDayKey } from '@/lib/format'

/**
 * Calendar arithmetic, in IST.
 *
 * Every date here is a `YYYY-MM-DD` string rather than a Date, because the
 * grid is a grid of Indian calendar days and a Date is an instant. An
 * instant is the wrong unit: 2026-11-02T00:00 in the browser's zone is a
 * different day in IST for anyone east or west of India, and this product
 * is Indian whoever is looking at it.
 *
 * The strings are compared and bucketed directly; only the two ends of a
 * window are turned back into instants, for the API.
 */

/** Weeks start on Monday — the Indian working week, and the calendar norm. */
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const

/** Today, as an IST day key. */
export function today(now: Date = new Date()): string {
  return istDayKey(now)
}

/** A day key `n` days later (or earlier, for a negative n). */
export function addDays(day: string, n: number): string {
  // Noon UTC, so adding whole days never crosses a boundary by rounding —
  // India has no daylight saving, but the midnight arithmetic is fragile
  // enough without relying on that.
  const base = new Date(`${day}T12:00:00Z`)
  base.setUTCDate(base.getUTCDate() + n)
  return base.toISOString().slice(0, 10)
}

export function addMonths(day: string, n: number): string {
  const [year, month] = day.split('-').map(Number)
  const base = new Date(Date.UTC(year!, month! - 1 + n, 1, 12))
  return base.toISOString().slice(0, 10)
}

/** 0 for Monday through 6 for Sunday. */
export function weekdayIndex(day: string): number {
  return (new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7
}

/** The Monday of the week `day` falls in. */
export function startOfWeek(day: string): string {
  return addDays(day, -weekdayIndex(day))
}

export function startOfMonth(day: string): string {
  return `${day.slice(0, 7)}-01`
}

/**
 * The days a month view draws: whole weeks, so the grid is rectangular and
 * the leading and trailing days of neighbouring months are visible rather
 * than blank.
 */
export function monthGrid(day: string): string[] {
  const first = startOfWeek(startOfMonth(day))
  const lastOfMonth = addDays(addMonths(startOfMonth(day), 1), -1)
  const last = addDays(startOfWeek(lastOfMonth), 6)

  const days: string[] = []
  for (let cursor = first; cursor <= last; cursor = addDays(cursor, 1)) days.push(cursor)
  return days
}

export function weekGrid(day: string): string[] {
  const first = startOfWeek(day)
  return Array.from({ length: 7 }, (_, i) => addDays(first, i))
}

export type CalendarView = 'week' | 'month'

export function gridFor(view: CalendarView, anchor: string): string[] {
  return view === 'week' ? weekGrid(anchor) : monthGrid(anchor)
}

/**
 * The half-open window a grid covers, as instants, for the API.
 *
 * Half-open because the API's filter is: a week and the week after it must
 * not both claim an item scheduled for exactly midnight on the boundary.
 */
export function windowFor(days: string[]): { from: string; to: string } {
  const first = days[0] ?? today()
  const last = days[days.length - 1] ?? first
  return { from: istMidnight(first), to: istMidnight(addDays(last, 1)) }
}

/** The instant an Indian calendar day begins. */
export function istMidnight(day: string): string {
  return `${day}T00:00:00+05:30`
}

/**
 * A day plus a time of day, as an instant.
 *
 * Dropping an item on a day keeps the hour it already had — moving a post
 * from Monday to Tuesday should not also move it from 09:00 to midnight.
 */
export function at(day: string, keepFrom: string | null): string {
  const time = keepFrom ? istClock(keepFrom) : '09:00:00'
  return `${day}T${time}+05:30`
}

const clock = new Intl.DateTimeFormat('en-GB', {
  timeZone: TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

/** "09:30:00" in IST, for rebuilding an instant on another day. */
export function istClock(instant: string): string {
  return clock.format(new Date(instant))
}

/** Items grouped by the IST day they are scheduled on. */
export function byDay<T extends { scheduled_at: string | null }>(
  items: readonly T[],
): Map<string, T[]> {
  const days = new Map<string, T[]>()
  for (const item of items) {
    if (!item.scheduled_at) continue
    const key = istDayKey(item.scheduled_at)
    const bucket = days.get(key)
    if (bucket) bucket.push(item)
    else days.set(key, [item])
  }
  return days
}

const monthName = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'UTC',
  month: 'long',
  year: 'numeric',
})

/** "November 2026", for the heading above a grid. */
export function monthLabel(day: string): string {
  return monthName.format(new Date(`${day}T12:00:00Z`))
}

const dayNumber = new Intl.DateTimeFormat('en-IN', { timeZone: 'UTC', day: 'numeric' })

/** "2", for the folio numeral in a day cell. */
export function dayLabel(day: string): string {
  return dayNumber.format(new Date(`${day}T12:00:00Z`))
}

const shortDate = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'UTC',
  day: '2-digit',
  month: 'short',
})

/** "2 Nov – 8 Nov", for a week heading. */
export function weekLabel(days: string[]): string {
  const first = days[0]
  const last = days[days.length - 1]
  if (!first || !last) return ''
  return `${shortDate.format(new Date(`${first}T12:00:00Z`))} – ${shortDate.format(
    new Date(`${last}T12:00:00Z`),
  )}`
}

const spoken = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'UTC',
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})

/** "Monday, 2 November", for accessible names on cells and buttons. */
export function spokenDate(day: string): string {
  return spoken.format(new Date(`${day}T12:00:00Z`))
}
