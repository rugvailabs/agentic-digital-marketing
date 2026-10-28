import { describe, expect, it } from 'vitest'

import { bucketOf, quantiles } from './HeatMap'

/**
 * The choropleth's scale. Worth testing because the first version was a
 * linear ramp and the map came out almost uniformly red — the failure was
 * invisible to every other kind of check.
 */

/** Today's real shape: 36 states, a third at zero, a long thin tail. */
const REAL = [
  0, 0, 0, 0.02, 0.04, 0.05, 0.07, 0.07, 0.07, 0.08, 0.1, 0.11, 0.12, 0.12, 0.12, 0.15, 0.15, 0.15,
  0.15, 0.17, 0.17, 0.19, 0.2, 0.23, 0.23, 0.23, 0.23, 0.25, 0.25, 0.3, 0.3, 0.31, 0.35, 0.35, 0.38,
  0.39,
]

describe('quantiles', () => {
  it('gives four interior cuts for five buckets', () => {
    expect(quantiles(REAL)).toHaveLength(4)
  })

  it('the cuts rise', () => {
    const cuts = quantiles(REAL)
    expect(cuts).toEqual([...cuts].sort((a, b) => a - b))
  })

  it('survives an empty day', () => {
    // Before the first ingest there is no heat at all, and the map still
    // has to draw 36 states rather than throw.
    expect(quantiles([])).toEqual([0, 0, 0, 0])
  })

  it('survives every state being identical', () => {
    const cuts = quantiles(Array.from({ length: 36 }, () => 0.2))
    expect(cuts.every((c) => c === 0.2)).toBe(true)
  })
})

describe('bucketOf', () => {
  const cuts = quantiles(REAL)

  it('uses the whole range on real data', () => {
    /** The point of quantiles. A linear ramp put 30 of these 36 states
     *  into two adjacent shades. */
    const used = new Set(REAL.map((share) => bucketOf(share, cuts)))

    expect(used.size).toBe(5)
  })

  it('spreads them evenly', () => {
    const counts = [0, 0, 0, 0, 0]
    for (const share of REAL) counts[bucketOf(share, cuts)]! += 1

    // 36 states over five buckets, so about seven each. Ties at zero make
    // the coldest bucket a little fuller, which is correct and not a bug.
    expect(Math.max(...counts)).toBeLessThanOrEqual(12)
    expect(Math.min(...counts)).toBeGreaterThan(0)
  })

  it('the quietest board is the coldest bucket', () => {
    expect(bucketOf(0, cuts)).toBe(0)
  })

  it('the busiest board is the hottest bucket', () => {
    expect(bucketOf(0.39, cuts)).toBe(4)
  })

  it('never goes out of range', () => {
    expect(bucketOf(99, cuts)).toBe(4)
    expect(bucketOf(-1, cuts)).toBe(0)
  })

  it('ties all land in the same bucket', () => {
    /** A third of the states share a value of exactly 0; splitting them
     *  across two shades would be inventing a difference. */
    const zeros = REAL.filter((s) => s === 0).map((s) => bucketOf(s, cuts))

    expect(new Set(zeros).size).toBe(1)
  })
})
