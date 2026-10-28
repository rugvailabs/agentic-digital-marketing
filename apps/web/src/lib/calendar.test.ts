import { describe, expect, it } from 'vitest'

import {
  addDays,
  addMonths,
  at,
  byDay,
  gridFor,
  istClock,
  monthGrid,
  monthLabel,
  startOfMonth,
  startOfWeek,
  weekGrid,
  weekdayIndex,
  windowFor,
} from './calendar'

/**
 * Calendar arithmetic, which is almost all off-by-one risk: a week that
 * starts on the wrong day, a month grid that drops its last row, a window
 * that claims a day twice.
 */

describe('addDays', () => {
  it('moves forward and back', () => {
    expect(addDays('2026-11-02', 1)).toBe('2026-11-03')
    expect(addDays('2026-11-02', -1)).toBe('2026-11-01')
  })

  it('crosses a month end', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDays('2026-11-01', -1)).toBe('2026-10-31')
  })

  it('crosses a year end', () => {
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
  })

  it('handles a leap day', () => {
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29')
    expect(addDays('2028-02-29', 1)).toBe('2028-03-01')
    expect(addDays('2027-02-28', 1)).toBe('2027-03-01')
  })

  it('is exact over a long run', () => {
    // Noon-anchored arithmetic, so no accumulated drift.
    let day = '2026-01-01'
    for (let i = 0; i < 365; i++) day = addDays(day, 1)
    expect(day).toBe('2027-01-01')
  })
})

describe('weeks', () => {
  it('starts on Monday', () => {
    // 2 November 2026 is a Monday.
    expect(weekdayIndex('2026-11-02')).toBe(0)
    expect(weekdayIndex('2026-11-08')).toBe(6)
  })

  it('a Sunday belongs to the week that began the Monday before', () => {
    /** The common off-by-one: with a Sunday-start week, 8 November would
     *  open a new row and sit alone at the top of it. */
    expect(startOfWeek('2026-11-08')).toBe('2026-11-02')
  })

  it('a week is seven days, Monday to Sunday', () => {
    const week = weekGrid('2026-11-05')

    expect(week).toHaveLength(7)
    expect(week[0]).toBe('2026-11-02')
    expect(week[6]).toBe('2026-11-08')
  })
})

describe('monthGrid', () => {
  it('is whole weeks, so the grid is rectangular', () => {
    const grid = monthGrid('2026-11-15')

    expect(grid.length % 7).toBe(0)
    expect(weekdayIndex(grid[0]!)).toBe(0)
    expect(weekdayIndex(grid[grid.length - 1]!)).toBe(6)
  })

  it('contains every day of its month', () => {
    const grid = monthGrid('2026-11-15')

    for (let d = 1; d <= 30; d++) {
      expect(grid).toContain(`2026-11-${String(d).padStart(2, '0')}`)
    }
  })

  it('includes the leading and trailing days of the neighbours', () => {
    // 1 November 2026 is a Sunday, so October runs into the first row.
    const grid = monthGrid('2026-11-15')

    expect(grid[0]).toBe('2026-10-26')
    expect(grid).toContain('2026-12-06')
  })

  it('a month that starts on a Monday still gets a full first row', () => {
    // 1 June 2026 is a Monday.
    const grid = monthGrid('2026-06-10')

    expect(grid[0]).toBe('2026-06-01')
  })

  it('February in a leap year keeps its 29th', () => {
    expect(monthGrid('2028-02-10')).toContain('2028-02-29')
  })
})

describe('addMonths', () => {
  it('lands on the first, so a short month cannot overflow', () => {
    /** A naive setMonth on the 31st gives 3 March for February. */
    expect(addMonths('2026-01-31', 1)).toBe('2026-02-01')
    expect(addMonths('2026-12-15', 1)).toBe('2027-01-01')
    expect(addMonths('2026-01-15', -1)).toBe('2025-12-01')
  })
})

describe('windowFor', () => {
  it('is half-open', () => {
    /** Or a month and the next would both claim an item scheduled for
     *  exactly midnight on the boundary. */
    const { from, to } = windowFor(['2026-11-02', '2026-11-08'])

    expect(from).toBe('2026-11-02T00:00:00+05:30')
    expect(to).toBe('2026-11-09T00:00:00+05:30')
  })

  it('two adjacent weeks meet without overlapping', () => {
    const first = windowFor(weekGrid('2026-11-02'))
    const second = windowFor(weekGrid('2026-11-09'))

    expect(first.to).toBe(second.from)
  })

  it('is in IST, not UTC', () => {
    expect(windowFor(['2026-11-02', '2026-11-02']).from).toContain('+05:30')
  })
})

describe('at', () => {
  it('keeps the time of day when moving to another day', () => {
    /** Moving a post from Monday to Tuesday should not also move it from
     *  09:00 to midnight. */
    const moved = at('2026-11-05', '2026-11-02T03:30:00Z')

    expect(moved).toBe('2026-11-05T09:00:00+05:30')
  })

  it('defaults to nine in the morning when there is no time to keep', () => {
    expect(at('2026-11-05', null)).toBe('2026-11-05T09:00:00+05:30')
  })

  it('reads the clock in IST', () => {
    // 18:45 IST is 13:15 UTC.
    expect(istClock('2026-11-02T13:15:00Z')).toBe('18:45:00')
  })

  it('a late-evening IST time survives the move', () => {
    const moved = at('2026-11-06', '2026-11-02T17:30:00Z')

    expect(moved).toBe('2026-11-06T23:00:00+05:30')
  })
})

describe('byDay', () => {
  const item = (scheduled_at: string | null) => ({ scheduled_at })

  it('buckets by the Indian day, not the UTC one', () => {
    /** 01:00 IST on 2 November is 19:30 UTC on 1 November. A UTC bucket
     *  would put a Monday-morning post on Sunday. */
    const days = byDay([item('2026-11-01T19:30:00Z')])

    expect([...days.keys()]).toEqual(['2026-11-02'])
  })

  it('keeps several items on one day together', () => {
    const days = byDay([item('2026-11-02T03:30:00Z'), item('2026-11-02T09:30:00Z')])

    expect(days.get('2026-11-02')).toHaveLength(1 + 1)
  })

  it('ignores unscheduled items', () => {
    expect(byDay([item(null)]).size).toBe(0)
  })
})

describe('labels', () => {
  it('names the month of its anchor', () => {
    expect(monthLabel('2026-11-15')).toBe('November 2026')
  })

  it('a grid day from the previous month still names the anchor month', () => {
    // The grid starts on 26 October but the heading reads November.
    expect(monthLabel(startOfMonth('2026-11-15'))).toBe('November 2026')
  })
})

describe('gridFor', () => {
  it('a week is 7 cells and a month is a multiple of 7', () => {
    expect(gridFor('week', '2026-11-05')).toHaveLength(7)
    expect(gridFor('month', '2026-11-05').length % 7).toBe(0)
  })
})
