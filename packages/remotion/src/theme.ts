/**
 * The design tokens from CLAUDE.md, and sizes expressed against the canvas.
 *
 * A reel is 1080x1920 and a square is 1080x1080, so nothing here is a fixed
 * pixel value: every size is a fraction of the width, the way the Pillow
 * templates do it. That is what lets one composition serve both shapes.
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

/** Fractions of the canvas width. */
export const scale = {
  margin: 0.08,
  eyebrow: 0.032,
  headline: 0.095,
  beat: 0.125,
  detail: 0.04,
  footer: 0.03,
  rule: 0.004,
} as const

/**
 * The band the type lives in, as fractions of the canvas height.
 *
 * Not the whole frame. A reel player draws its own furniture over both ends —
 * the account and the sound ribbon at the top, the caption and the action
 * column at the bottom — and type centred in 1920px of canvas ends up in the
 * half nobody reads, floating in dead space. These insets put the block at
 * roughly 42% down on a 9:16, which is where the eye actually lands.
 */
export const band = {
  reel: { top: 0.14, bottom: 0.3 },
  square: { top: 0.1, bottom: 0.2 },
} as const

export function px(width: number, fraction: number): number {
  return Math.round(width * fraction)
}

/**
 * Motion budget, in frames at 30fps.
 *
 * CLAUDE.md allows one load-in and motion that answers an action, and nothing
 * else. In a video the type has to arrive somehow, so it arrives the same way
 * the ladder rows do — a short settle from below — and nothing zooms, spins
 * or fades through a gradient.
 */
export const motion = {
  settle: 9,
  /** How far type travels on the way in, as a fraction of the width. */
  travel: 0.022,
  /** Frames the rule takes to wipe across. */
  wipe: 12,
} as const
