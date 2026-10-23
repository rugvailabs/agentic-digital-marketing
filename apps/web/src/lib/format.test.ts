import { describe, expect, it } from 'vitest'

import {
  formatCompactVolume,
  formatIstDateTime,
  formatIstTime,
  formatNumber,
  shortCategory,
  velocityTrend,
} from './format'

describe('en-IN number formatting', () => {
  it('groups in lakhs, not thousands', () => {
    // The whole point: en-US would render 2,00,000 as 200,000.
    expect(formatNumber(200000)).toBe('2,00,000')
    expect(formatNumber(10000000)).toBe('1,00,00,000')
    expect(formatNumber(999)).toBe('999')
  })

  it('compacts volume for the ladder column', () => {
    expect(formatCompactVolume(200000)).toBe('2L')
    expect(formatCompactVolume(150000)).toBe('1.5L')
    expect(formatCompactVolume(12000000)).toBe('1.2Cr')
    expect(formatCompactVolume(4820)).toBe('4.8K')
    expect(formatCompactVolume(820)).toBe('820')
  })

  it('shows an em dash rather than a zero when no source reported volume', () => {
    expect(formatCompactVolume(0)).toBe('—')
  })
})

describe('IST formatting', () => {
  // 2026-10-23T06:15:00Z is 11:45 IST (+5:30).
  const instant = '2026-10-23T06:15:00Z'

  it('renders the clock in IST regardless of the host timezone', () => {
    expect(formatIstTime(instant)).toBe('11:45')
  })

  it('renders dates in Indian order', () => {
    expect(formatIstDateTime(instant)).toMatch(/^23 Oct, 11:45$/)
  })

  it('accepts Date objects as well as ISO strings', () => {
    expect(formatIstTime(new Date(instant))).toBe('11:45')
  })
})

describe('velocityTrend', () => {
  it('calls a topic rising when it clears the dead band', () => {
    expect(velocityTrend([10, 10, 10, 10, 10, 20])).toBe('rising')
  })

  it('calls a topic cooling when it falls below the dead band', () => {
    expect(velocityTrend([80, 80, 80, 80, 80, 20])).toBe('cooling')
  })

  it('treats small movement as settled, so rows do not flicker on rank noise', () => {
    expect(velocityTrend([100, 100, 100, 100, 100, 105])).toBe('settled')
    expect(velocityTrend([100, 100, 100, 100, 100, 95])).toBe('settled')
  })

  it('reads a brand new topic as rising, since the API left-pads with zeros', () => {
    expect(velocityTrend([0, 0, 0, 0, 0, 42])).toBe('rising')
  })

  it('reads a dropped-off topic as cooling', () => {
    expect(velocityTrend([90, 80, 50, 20, 10, 0])).toBe('cooling')
  })

  it('is settled rather than undefined for degenerate series', () => {
    expect(velocityTrend([])).toBe('settled')
    expect(velocityTrend([5])).toBe('settled')
    expect(velocityTrend([0, 0, 0, 0, 0, 0])).toBe('settled')
  })
})

describe('shortCategory', () => {
  it('shortens the long Google Trends names that do not fit a ladder chip', () => {
    expect(shortCategory('Business and Finance')).toBe('Business')
    expect(shortCategory('Law and Government')).toBe('Law')
    expect(shortCategory('Travel and Transportation')).toBe('Travel')
    expect(shortCategory('Technology')).toBe('Tech')
  })

  it('passes through names that are already short, including unknown ones', () => {
    expect(shortCategory('Sports')).toBe('Sports')
    expect(shortCategory('Politics')).toBe('Politics')
    expect(shortCategory('Something New')).toBe('Something New')
  })
})
