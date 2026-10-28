import type { Brand } from '@trendforge/types'
import { describe, expect, it } from 'vitest'

import { contrastingInk, formOf, linesOf, textOf } from './brand'

/** WCAG relative luminance, for asserting the ratios the threshold claims. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
  const ch = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * ch(r!) + 0.7152 * ch(g!) + 0.0722 * ch(b!)
}

function ratio(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (high! + 0.05) / (low! + 0.05)
}

/**
 * The preview's maths, which is where it either keeps or breaks its promise
 * about what the renderer will do.
 */

describe('contrastingInk', () => {
  /**
   * The same cases the Pillow version is held to. The preview tells a user
   * their headline will be legible on their brand colour; if the two rules
   * disagree, that is a lie at exactly the colours someone is least sure
   * about.
   */
  it.each([
    ['#1B2230', '#FFFFFF', 'the board ink'],
    ['#D8322B', '#FFFFFF', 'chilli'],
    ['#EEF1F6', '#1B2230', 'paper'],
    ['#E3A51D', '#1B2230', 'turmeric, which white fails at 2.2:1'],
    ['#FFFFFF', '#1B2230', 'white'],
    ['#000000', '#FFFFFF', 'black'],
  ])('%s takes %s (%s)', (background, ink) => {
    expect(contrastingInk(background)).toBe(ink)
  })

  it('uses luminance rather than an average', () => {
    /**
     * A saturated red and a mid grey can share a channel average and need
     * opposite text colours. Green carries most of the luminance, which an
     * average throws away.
     */
    expect(contrastingInk('#808080')).toBe('#1B2230')
    expect(contrastingInk('#FF0000')).toBe('#FFFFFF')
    expect(contrastingInk('#00FF00')).toBe('#1B2230')
    // Same channel average as #00FF00, opposite answer.
    expect(contrastingInk('#0000FF')).toBe('#FFFFFF')
  })

  it('expands three-digit hex', () => {
    expect(contrastingInk('#FFF')).toBe(contrastingInk('#FFFFFF'))
    expect(contrastingInk('#000')).toBe(contrastingInk('#000000'))
  })

  it('falls back rather than throwing on a half-typed colour', () => {
    // The field is a text input, so every intermediate value arrives here.
    // What it returns matters less than that it returns: a thrown error
    // here blanks the preview mid-keystroke.
    for (const half of ['#2B1A', '', 'coffee', '#']) {
      expect(['#FFFFFF', '#1B2230']).toContain(contrastingInk(half))
    }
  })

  it('every colour in the design system clears 4.5:1 against its ink', () => {
    /**
     * The threshold is derived rather than chosen, so this is the claim it
     * was derived to make. #D8322B against white is 4.76:1 and is the
     * tightest of them.
     */
    for (const colour of ['#1B2230', '#D8322B', '#EEF1F6', '#E3A51D', '#1E7D5A', '#FFFFFF']) {
      expect(ratio(colour, contrastingInk(colour))).toBeGreaterThanOrEqual(4.5)
    }
  })
})

describe('textarea lists', () => {
  it('drops blank lines and trims', () => {
    expect(linesOf('  Cold brew  \n\n   \nFilters')).toEqual(['Cold brew', 'Filters'])
  })

  it('an empty textarea is an empty list, not a list with one empty string', () => {
    expect(linesOf('')).toEqual([])
    expect(linesOf('\n\n')).toEqual([])
  })

  it('round trips', () => {
    const lines = ['Cold brew', 'Filters']
    expect(linesOf(textOf(lines))).toEqual(lines)
  })
})

describe('formOf', () => {
  it('a new brand starts on the board palette', () => {
    const form = formOf(null)

    expect(form.primary_color).toBe('#1B2230')
    expect(form.secondary_color).toBe('#D8322B')
    expect(form.languages).toEqual(['english'])
    expect(form.font_choice).toBe('display')
  })

  it('an existing brand keeps every field', () => {
    const brand: Brand = {
      id: 7,
      slug: 'madras-filter-coffee',
      name: 'Madras Filter Coffee',
      voice_prompt: 'Warm and dry.',
      logo_url: 'http://minio/logo.png',
      primary_color: '#2B1A12',
      secondary_color: '#E3A51D',
      languages: ['english', 'tamil'],
      font_choice: 'ui',
      products: ['Cold brew'],
      default_region_code: 'IN-TN',
      do_not_mention: ['pricing'],
    }

    expect(formOf(brand)).toEqual({
      name: 'Madras Filter Coffee',
      slug: 'madras-filter-coffee',
      voice_prompt: 'Warm and dry.',
      primary_color: '#2B1A12',
      secondary_color: '#E3A51D',
      languages: ['english', 'tamil'],
      font_choice: 'ui',
      products: ['Cold brew'],
      default_region_code: 'IN-TN',
      do_not_mention: ['pricing'],
    })
  })
})
