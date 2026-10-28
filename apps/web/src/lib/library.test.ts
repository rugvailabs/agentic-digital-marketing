import { describe, expect, it } from 'vitest'

import { formatAge, istDayKey } from './format'
import { libraryQuery } from './library'

describe('libraryQuery', () => {
  it('is empty when nothing is filtered', () => {
    expect(libraryQuery({})).toBe('')
  })

  it('encodes a timestamp offset', () => {
    /**
     * The one that bites. An ISO timestamp ends in "+05:30", and a raw "+"
     * in a query string is a space — so a hand-built URL turns a date
     * filter into a 422 about "unexpected extra characters".
     */
    const query = libraryQuery({ created_from: '2026-10-27T00:00:00+05:30' })

    expect(query).toContain('%2B05%3A30')
    expect(query).not.toContain('+05:30')
  })

  it('round trips through URLSearchParams', () => {
    const stamp = '2026-10-27T00:00:00+05:30'
    const parsed = new URLSearchParams(libraryQuery({ created_from: stamp }))

    expect(parsed.get('created_from')).toBe(stamp)
  })

  it('drops empty values rather than sending them', () => {
    // A cleared select is "", and `?region=` is not the same request as no
    // region at all.
    const query = libraryQuery({ region: '', q: undefined, kind: 'post' })

    expect(query).toBe('?kind=post')
  })

  it('escapes a search term', () => {
    expect(libraryQuery({ q: 'goa & ai' })).toBe('?q=goa+%26+ai')
  })
})

describe('formatAge', () => {
  const now = new Date('2026-10-28T12:00:00+05:30')

  it.each([
    ['2026-10-28T11:59:40+05:30', 'just now'],
    ['2026-10-28T11:30:00+05:30', '30 min ago'],
    ['2026-10-28T11:00:00+05:30', '1 hour ago'],
    ['2026-10-28T06:00:00+05:30', '6 hours ago'],
    ['2026-10-27T12:00:00+05:30', 'yesterday'],
    ['2026-10-25T12:00:00+05:30', '3 days ago'],
  ])('%s reads as %s', (stamp, expected) => {
    expect(formatAge(stamp, now)).toBe(expected)
  })

  it('gives a date once relative stops helping', () => {
    /**
     * Nobody counts back from today to find last month's work, and the
     * library sorts newest first — so past a week the exact date is what
     * distinguishes one old item from another.
     */
    // "Sept", not "Sep": that is what en-IN calls it, and the whole point
    // of pinning the locale is that the app does not follow the viewer's.
    expect(formatAge('2026-09-14T12:00:00+05:30', now)).toBe('14 Sept 2026')
  })
})

describe('istDayKey', () => {
  it('is the Indian day, not the UTC one', () => {
    /**
     * 01:00 IST is 19:30 UTC the day before, so a UTC day key would put a
     * post scheduled for Monday morning on Sunday in the calendar grid.
     */
    expect(istDayKey('2026-11-02T01:00:00+05:30')).toBe('2026-11-02')
    expect(new Date('2026-11-02T01:00:00+05:30').toISOString().slice(0, 10)).toBe('2026-11-01')
  })

  it('holds through the end of an Indian day', () => {
    expect(istDayKey('2026-11-02T23:59:00+05:30')).toBe('2026-11-02')
    expect(istDayKey('2026-11-03T00:01:00+05:30')).toBe('2026-11-03')
  })
})
