/**
 * The edition line: one segment per card, filling as that card plays.
 *
 * A single bar filling over the whole reel told the viewer how far through
 * they were and nothing else. Segmented, it also says how many beats there
 * are and which one is running — the same thing the ladder's rank numerals
 * do, and it means the bar is tied to the actual edit rather than to a
 * stopwatch laid over it.
 *
 * Chilli for played, rule for pending. Chilli already means "moving" on the
 * board and this is the one place in a reel where something moves by design.
 */

import { interpolate, useCurrentFrame } from 'remotion'

import { colours } from '../theme'

export function Ticker({
  segments,
  height,
  gap,
}: {
  /** Frame count of each card, in order. */
  segments: number[]
  height: number
  gap: number
}) {
  const frame = useCurrentFrame()
  let start = 0

  return (
    <div style={{ display: 'flex', gap, width: '100%' }}>
      {segments.map((frames, index) => {
        const played = interpolate(frame, [start, start + frames], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        })
        start += frames
        return (
          <div
            // Index, not duration: two cards can legitimately run the same
            // length.
            key={index}
            style={{
              // Proportional to the card's length, so the segments are a
              // picture of the edit rather than equal thirds.
              flex: frames,
              height,
              backgroundColor: colours.rule,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${played * 100}%`,
                height: '100%',
                backgroundColor: colours.chilli,
              }}
            />
          </div>
        )
      })}
    </div>
  )
}
