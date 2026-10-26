/**
 * The one motion in the whole system: type arrives from just below and
 * settles, the way the ladder rows do on load.
 *
 * CLAUDE.md allows one load-in and motion that answers an action, and nothing
 * else. A video has to get its type on screen somehow, so it gets it on the
 * same way — no zoom, no fade through a gradient, no letter-by-letter.
 */

import type { ReactNode } from 'react'
import { interpolate, useCurrentFrame } from 'remotion'

import { motion } from '../theme'

/** Fast off the mark, settling rather than gliding to a stop. */
const outCubic = (t: number): number => 1 - Math.pow(1 - t, 3)

const CLAMP = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const

export function Settle({
  children,
  delay = 0,
  travel,
  frames = motion.settle,
}: {
  children: ReactNode
  /** Frames to wait before starting, for staggering a stack of lines. */
  delay?: number
  /** Distance travelled, in pixels. Scaled by the caller against the canvas. */
  travel: number
  frames?: number
}) {
  const frame = useCurrentFrame() - delay
  const progress = interpolate(frame, [0, frames], [0, 1], { ...CLAMP, easing: outCubic })

  return (
    <div
      style={{
        opacity: interpolate(frame, [0, frames * 0.6], [0, 1], CLAMP),
        transform: `translateY(${(1 - progress) * travel}px)`,
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
  frames = motion.wipe,
}: {
  delay?: number
  width: number
  height: number
  colour: string
  frames?: number
}) {
  const frame = useCurrentFrame() - delay
  const grown = interpolate(frame, [0, frames], [0, width], { ...CLAMP, easing: outCubic })

  return <div style={{ width: grown, height, backgroundColor: colour }} />
}
