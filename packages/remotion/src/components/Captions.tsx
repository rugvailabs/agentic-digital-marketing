/**
 * Burned-in captions, one sentence at a time.
 *
 * Not a nicety. Most reels play muted on a feed, so a reel whose argument
 * lives only in the voiceover is a reel nobody hears — and burned in rather
 * than left to the platform, because a platform's auto-captions mangle
 * "two crore" and are not there at all on a download.
 *
 * They sit in the bottom third, between the card band and the footer: clear
 * of the type above, clear of the caption and account row a reel player draws
 * over the bottom. The active sentence carries the brand colour, which is the
 * one place in a frame where a brand's own colour appears.
 */

import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'

import type { CaptionProps } from '../props'
import { type Format, colours, px } from '../theme'
import { fitLines } from '../typography'

/** Frames to fade a sentence in and out. Short: a caption that drifts is
 *  harder to read than one that simply changes. */
const FADE = 4

export function Captions({
  captions,
  format,
  fonts,
  accent,
}: {
  captions: CaptionProps[]
  format: Format
  fonts: { display: string; ui: string }
  accent: string
}) {
  const frame = useCurrentFrame()
  const { width, height } = useVideoConfig()

  // The last one that has started. Sentences are contiguous by construction,
  // so this is also the one being spoken.
  let active: CaptionProps | null = null
  for (const caption of captions) {
    if (frame >= caption.fromFrame && frame < caption.fromFrame + caption.frames) {
      active = caption
      break
    }
  }
  if (!active) return null

  const margin = px(width, format.margin)
  const measure = width - margin * 2
  const size = px(width, format.caption)

  const fitted = fitLines({
    text: active.text,
    maxWidth: measure - px(width, 0.03),
    // Three lines at this size is the whole band; a longer sentence steps
    // down rather than growing into the footer.
    maxHeight: size * 3.6,
    maxFontSize: size,
    minFontSize: Math.round(size * 0.62),
    fontFamily: fonts.ui,
    fontWeight: 600,
    leading: 1.22,
    maxLines: 3,
  })

  const local = frame - active.fromFrame
  const opacity =
    interpolate(local, [0, FADE], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    }) *
    interpolate(local, [active.frames - FADE, active.frames], [1, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    })

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left: margin,
          right: margin,
          // Above the footer and below the card band: the bottom third,
          // inside the margins every platform crops into.
          bottom: Math.round(height * format.captionBottom),
          display: 'flex',
          justifyContent: 'flex-start',
          opacity,
        }}
      >
        <div
          style={{
            display: 'flex',
            // A block behind the text, not bare type on paper. Captions are
            // read at a glance on a small screen, and the grain and the
            // sparkline both pass behind this band.
            backgroundColor: colours.surface,
            borderLeft: `${px(width, 0.008)}px solid ${accent}`,
            padding: `${px(width, 0.022)}px ${px(width, 0.028)}px`,
            maxWidth: '100%',
          }}
        >
          <div
            style={{
              fontFamily: fonts.ui,
              fontWeight: 600,
              fontSize: fitted.fontSize,
              lineHeight: `${fitted.lineHeight}px`,
              color: colours.ink,
              letterSpacing: '-0.005em',
              overflowWrap: 'anywhere',
            }}
          >
            {fitted.lines.map((line, index) => (
              <div key={index}>{line}</div>
            ))}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  )
}
