/**
 * The one motion in the system: type arrives from just below and settles, the
 * way the ladder rows do on load, and leaves the same way.
 *
 * A card both enters and exits. Without the exit, every change of card is a
 * hard cut from full-contrast type to full-contrast type, which on a 30fps
 * reel reads as a glitch rather than as an edit.
 */

import type { ReactNode } from 'react'
import { interpolate, useCurrentFrame } from 'remotion'

import { motion } from '../theme'

/** Fast off the mark, settling rather than gliding to a stop. */
export const outCubic = (t: number): number => 1 - Math.pow(1 - t, 3)
/** The mirror, for leaving: slow to go, then gone. */
export const inCubic = (t: number): number => t * t * t

const CLAMP = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const

export function Reveal({
  children,
  delay = 0,
  travel,
  /** Length of the card this sits in. Omit for furniture that never leaves. */
  cardFrames,
  enterFrames = motion.enter,
}: {
  children: ReactNode
  delay?: number
  travel: number
  cardFrames?: number
  enterFrames?: number
}) {
  const frame = useCurrentFrame()

  const entered = interpolate(frame - delay, [0, enterFrames], [0, 1], {
    ...CLAMP,
    easing: outCubic,
  })
  // Every line of a block leaves together. Staggering the exit as well as the
  // entrance reads as fussy, and nobody is reading the last line on its way
  // out anyway.
  const left =
    cardFrames === undefined
      ? 0
      : interpolate(frame, [cardFrames - motion.exit, cardFrames], [0, 1], {
          ...CLAMP,
          easing: inCubic,
        })

  return (
    <div
      style={{
        opacity: interpolate(frame - delay, [0, enterFrames * 0.55], [0, 1], CLAMP) * (1 - left),
        // Out the way it came in, but a shorter distance: a full-height exit
        // draws the eye to the thing that is leaving.
        transform: `translateY(${(1 - entered) * travel - left * travel * 0.55}px)`,
      }}
    >
      {children}
    </div>
  )
}

/** A rule that wipes across rather than appearing. */
export function Wipe({
  delay = 0,
  width,
  height,
  colour,
  cardFrames,
  frames = motion.wipe,
}: {
  delay?: number
  width: number
  height: number
  colour: string
  cardFrames?: number
  frames?: number
}) {
  const frame = useCurrentFrame()
  const grown = interpolate(frame - delay, [0, frames], [0, width], {
    ...CLAMP,
    easing: outCubic,
  })
  const left =
    cardFrames === undefined
      ? 0
      : interpolate(frame, [cardFrames - motion.exit, cardFrames], [0, 1], {
          ...CLAMP,
          easing: inCubic,
        })

  return <div style={{ width: grown, height, backgroundColor: colour, opacity: 1 - left }} />
}
