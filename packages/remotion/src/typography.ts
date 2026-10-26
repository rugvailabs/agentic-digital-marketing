/**
 * Measured line fitting, the same idea as `fit_text` in the Pillow templates.
 *
 * Sizes are not fixed fractions of the canvas. A headline is set as large as
 * it can be and still fit its box, so a three-word beat is enormous and a
 * long one steps down and wraps — which is where the scale contrast in these
 * frames comes from, and why a different topic does not need a different
 * layout.
 *
 * Measured rather than counted, because character count is a poor proxy for
 * width in any script and a useless one in Tamil or Devanagari, where one
 * word can carry what English needs three for and cannot be broken at a
 * space.
 */

import { measureText } from '@remotion/layout-utils'

export type Fitted = {
  lines: string[]
  fontSize: number
  /** Pixels, already multiplied out — the caller sets it directly. */
  lineHeight: number
}

export type FitOptions = {
  text: string
  maxWidth: number
  maxHeight: number
  maxFontSize: number
  minFontSize: number
  fontFamily: string
  fontWeight: number
  /** Multiple of the font size. Display type wants this tight. */
  leading?: number
  maxLines?: number
}

/** 4% a step: fine enough that the result looks deliberate, coarse enough
 *  that the search is a dozen measurements rather than a hundred. */
const STEP = 0.96

function widthOf(text: string, fontFamily: string, fontSize: number, fontWeight: number): number {
  if (!text) return 0
  return measureText({ text, fontFamily, fontSize, fontWeight: String(fontWeight) }).width
}

/** Greedy wrap at a given size. A word wider than the box gets its own line
 *  and is left to `overflow-wrap` at render time. */
export function wrapText(
  text: string,
  fontFamily: string,
  fontSize: number,
  fontWeight: number,
  maxWidth: number,
): string[] {
  const words = text.split(/\s+/).filter(Boolean)
  if (words.length === 0) return ['']

  const lines: string[] = []
  let current = ''

  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word
    if (current && widthOf(candidate, fontFamily, fontSize, fontWeight) > maxWidth) {
      lines.push(current)
      current = word
    } else {
      current = candidate
    }
  }
  if (current) lines.push(current)
  return lines
}

/**
 * Even out the rag without changing the line count.
 *
 * Greedy wrapping fills each line to the edge and leaves whatever is left on
 * the last one, which at display sizes produces "Goa has / an AI / policy" —
 * a full line, then two short ones. Narrowing the box until it is about to
 * need an extra line spreads the words evenly instead, which is what
 * `text-wrap: balance` does; it cannot be used here because each line is its
 * own element so it can be animated separately.
 *
 * The search is monotonic — narrower never means fewer lines — so a binary
 * search is exact. Roughly ten more measurements, and the whole fit is
 * memoised per card.
 */
function balance(
  text: string,
  fontFamily: string,
  fontSize: number,
  fontWeight: number,
  maxWidth: number,
  targetLines: number,
  fallback: string[],
): string[] {
  if (targetLines < 2) return fallback

  let low = 1
  let high = maxWidth
  let best = fallback

  while (low < high) {
    const mid = Math.floor((low + high) / 2)
    const lines = wrapText(text, fontFamily, fontSize, fontWeight, mid)
    if (lines.length <= targetLines) {
      best = lines
      high = mid
    } else {
      low = mid + 1
    }
  }
  return best
}

/**
 * The largest size at which `text` fits the box, stepping down.
 *
 * Both dimensions are checked. A single long word passes a height-only check
 * and still runs off the edge, which is the failure mode that actually shows
 * up — in Telugu, on the one frame nobody screenshotted.
 */
export function fitLines(options: FitOptions): Fitted {
  const { text, maxWidth, maxHeight, minFontSize, fontFamily, fontWeight } = options
  const leading = options.leading ?? 1.05
  const maxLines = options.maxLines ?? 6

  let size = Math.max(options.maxFontSize, minFontSize)
  let last: Fitted | null = null

  while (size >= minFontSize) {
    const lines = wrapText(text, fontFamily, size, fontWeight, maxWidth)
    const lineHeight = Math.round(size * leading)
    const widest = lines.reduce(
      (most, line) => Math.max(most, widthOf(line, fontFamily, size, fontWeight)),
      0,
    )

    last = { lines, fontSize: size, lineHeight }
    if (lines.length <= maxLines && lines.length * lineHeight <= maxHeight && widest <= maxWidth) {
      return {
        ...last,
        lines: balance(text, fontFamily, size, fontWeight, maxWidth, lines.length, lines),
      }
    }
    size = Math.floor(size * STEP)
  }

  // Nothing fit. Return the smallest attempt rather than nothing at all: a
  // slightly tight frame is recoverable, a blank one is not.
  return last ?? { lines: [text], fontSize: minFontSize, lineHeight: minFontSize }
}
