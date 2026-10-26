/**
 * The design tokens from CLAUDE.md, and a layout per format.
 *
 * Nothing here is a fixed pixel value: every size is a fraction of the canvas,
 * the way the Pillow templates do it. That is what lets one composition serve
 * 9:16 and 1:1 without two layouts to keep in step.
 */

export const colours = {
  paper: '#EEF1F6',
  ink: '#1B2230',
  slate: '#5B6578',
  rule: '#D5DAE3',
  chilli: '#D8322B',
  neem: '#1E7D5A',
  turmeric: '#E3A51D',
  surface: '#FFFFFF',
} as const

export type Format = {
  /** Text column, as a fraction of the width. */
  measure: number
  margin: number
  /** The band the card content lives in, as fractions of the height. */
  band: { top: number; bottom: number }
  /** Search bounds for the measured fit, as fractions of the width. */
  headline: { max: number; min: number }
  beat: { max: number; min: number }
  maxLines: number
  detail: number
  label: number
  footer: number
  /** Caption type size, as a fraction of the width. */
  caption: number
  /** Where the caption block sits, as a fraction of the height from the
   *  bottom: above the footer, below the card band. */
  captionBottom: number
  /** Height of the closing chart, as a fraction of the width. */
  chart: number
  /** Furniture positions, as fractions of the height. */
  ticker: number
  masthead: number
  footerBottom: number
}

/**
 * Reel measure is 72%, not the full column.
 *
 * Two reasons, and they pull the same way. A reel player stacks its action
 * column — like, comment, share, sound — down the right-hand side, so type
 * running to the right margin sits under buttons. And a narrower measure
 * means more lines at a larger size, which is what fills a 1920px canvas that
 * otherwise reads as three words floating in a lot of paper.
 */
export const formats: Record<'reel' | 'square', Format> = {
  reel: {
    measure: 0.72,
    margin: 0.08,
    // Bottom is wide on purpose: a reel's caption and account row cover the
    // lower fifth, and anything there is read through them.
    band: { top: 0.145, bottom: 0.3 },
    headline: { max: 0.175, min: 0.052 },
    beat: { max: 0.23, min: 0.062 },
    maxLines: 5,
    detail: 0.042,
    label: 0.031,
    footer: 0.03,
    caption: 0.038,
    captionBottom: 0.155,
    chart: 0.3,
    ticker: 0.031,
    masthead: 0.058,
    footerBottom: 0.082,
  },
  square: {
    // A square has no action column over the artwork, so it keeps its column.
    measure: 0.9,
    margin: 0.075,
    band: { top: 0.17, bottom: 0.19 },
    headline: { max: 0.125, min: 0.04 },
    beat: { max: 0.155, min: 0.046 },
    maxLines: 4,
    detail: 0.033,
    label: 0.027,
    footer: 0.027,
    caption: 0.034,
    captionBottom: 0.145,
    chart: 0.2,
    ticker: 0.034,
    masthead: 0.066,
    footerBottom: 0.075,
  },
}

export function formatFor(width: number, height: number): Format {
  return height / width > 1.3 ? formats.reel : formats.square
}

/**
 * Line height, as a multiple of the font size.
 *
 * Display type wants it tight. Indic scripts want considerably more room:
 * Tamil and Devanagari stack marks above and below the base character, so the
 * Latin number has "ஏஐ" sitting on top of "கொள்கை".
 */
export const leading = { latin: 1.05, indic: 1.32 } as const

export function px(width: number, fraction: number): number {
  return Math.round(width * fraction)
}

/**
 * Motion budget, in frames at 30fps.
 *
 * CLAUDE.md allows one load-in and motion that answers an action, and nothing
 * else. A video has to get its type on screen somehow, so it arrives the same
 * way the ladder rows do — a short settle from below, staggered line by line
 * — and leaves the same way. Nothing zooms, spins, or animates letter by
 * letter.
 */
export const motion = {
  enter: 11,
  exit: 7,
  /** Per line of a block. Enough to read as a sweep, not as a queue. */
  stagger: 3,
  /** Distance type travels on the way in, as a fraction of the width. */
  travel: 0.024,
  /** Frames a rule takes to wipe across. */
  wipe: 14,
} as const
