/**
 * The wire desk as motion.
 *
 * Paper ground, ink type, one chilli rule, and a thin chilli ticker along the
 * top that fills as the reel runs — the newsroom equivalent of a progress bar,
 * and the only thing on screen that is there purely to orient the viewer.
 *
 * Structure: an opening card with the region and the headline, one card per
 * beat, then a closing card with the sparkline, the hashtags and the brand.
 * The same component serves 9:16 and 1:1; every size is a fraction of the
 * width, so the square is the reel with less vertical room rather than a
 * second layout to keep in step.
 */

import { AbsoluteFill, Sequence, interpolate, useCurrentFrame, useVideoConfig } from 'remotion'

import { Settle, Wipe } from '../components/Settle'
import { Sparkline } from '../components/Sparkline'
import { useFonts } from '../fonts'
import { OUTRO_FRAMES, TITLE_FRAMES, type ReelProps, withDefaults } from '../props'
import { band, colours, motion, px, scale } from '../theme'

export const Wire: React.FC<ReelProps> = (raw) => {
  // Guarded rather than trusted: these arrive from another process, and a
  // missing beats array is a stack trace in a headless Chromium log rather
  // than anything a user could act on.
  const props = withDefaults(raw)
  const { width, height, durationInFrames } = useVideoConfig()
  const fonts = useFonts(props.script)

  const margin = px(width, scale.margin)
  const travel = px(width, motion.travel)
  // A square has roughly half the vertical room, so type that is comfortable
  // on a reel has to come down. One factor rather than a second set of sizes.
  const tall = height / width > 1.3
  const squeeze = tall ? 1 : 0.76
  const inset = tall ? band.reel : band.square

  let cursor = TITLE_FRAMES

  return (
    <AbsoluteFill style={{ backgroundColor: colours.paper, fontKerning: 'normal' }}>
      <Ticker width={width} height={px(width, 0.007)} duration={durationInFrames} />

      <Sequence durationInFrames={TITLE_FRAMES} name="Title">
        <Title
          props={props}
          margin={margin}
          inset={inset}
          travel={travel}
          squeeze={squeeze}
          fonts={fonts}
        />
      </Sequence>

      {props.beats.map((beat, index) => {
        const from = cursor
        cursor += beat.frames
        return (
          <Sequence
            // Index, not text: two beats can legitimately read the same, and
            // a duplicate key makes Remotion reuse one of their trees.
            key={index}
            from={from}
            durationInFrames={beat.frames}
            name={`Beat ${index + 1}`}
          >
            <BeatCard
              beat={beat}
              index={index}
              total={props.beats.length}
              margin={margin}
              inset={inset}
              travel={travel}
              squeeze={squeeze}
              fonts={fonts}
              accent={props.secondaryColor}
            />
          </Sequence>
        )
      })}

      <Sequence from={cursor} durationInFrames={OUTRO_FRAMES} name="Outro">
        <Outro
          props={props}
          margin={margin}
          inset={inset}
          travel={travel}
          squeeze={squeeze}
          fonts={fonts}
        />
      </Sequence>

      <Footer props={props} margin={margin} fonts={fonts} />
    </AbsoluteFill>
  )
}

/** Fills across the top over the whole reel. Chilli, like rising velocity. */
function Ticker({ width, height, duration }: { width: number; height: number; duration: number }) {
  const frame = useCurrentFrame()
  const grown = interpolate(frame, [0, duration], [0, width], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  })

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, width, height }}>
      <div style={{ width: grown, height, backgroundColor: colours.chilli }} />
    </div>
  )
}

type Inset = { top: number; bottom: number }

type CardProps = {
  margin: number
  inset: Inset
  travel: number
  squeeze: number
  fonts: { display: string; ui: string }
}

function Title({ props, margin, inset, travel, squeeze, fonts }: CardProps & { props: ReelProps }) {
  const { width } = useVideoConfig()
  const eyebrow = props.regionName ? `Trending in ${props.regionName}` : 'Trending now'

  return (
    <Card margin={margin} inset={inset}>
      <Settle travel={travel}>
        <div
          style={{
            fontFamily: fonts.ui,
            fontSize: px(width, scale.eyebrow),
            fontWeight: 600,
            color: colours.slate,
            letterSpacing: '0.01em',
          }}
        >
          {eyebrow}
        </div>
      </Settle>

      <div style={{ height: px(width, 0.03) }} />
      <Wipe
        delay={4}
        width={px(width, 0.2)}
        height={px(width, scale.rule)}
        colour={colours.chilli}
      />
      <div style={{ height: px(width, 0.045) }} />

      <Settle delay={6} travel={travel}>
        <div
          style={{
            fontFamily: fonts.display,
            fontSize: px(width, scale.headline * squeeze),
            fontWeight: 800,
            lineHeight: 1.05,
            color: colours.ink,
            // Long Tamil and Telugu words cannot be broken at a space, and a
            // word running off the canvas is worse than a hyphen.
            overflowWrap: 'anywhere',
          }}
        >
          {props.headline}
        </div>
      </Settle>
    </Card>
  )
}

function BeatCard({
  beat,
  index,
  total,
  margin,
  inset,
  travel,
  squeeze,
  fonts,
  accent,
}: CardProps & {
  beat: { text: string; detail: string }
  index: number
  total: number
  accent: string
}) {
  const { width } = useVideoConfig()

  return (
    <Card margin={margin} inset={inset}>
      <Settle travel={travel}>
        <div
          style={{
            fontFamily: fonts.ui,
            fontSize: px(width, scale.eyebrow * 0.9),
            fontWeight: 600,
            // Slate, not chilli: this is a position, not a velocity. The
            // numerals are the display face, like the ladder's rank folio.
            color: colours.slate,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {index + 1} / {total}
        </div>
      </Settle>

      <div style={{ height: px(width, 0.035) }} />

      <Settle delay={3} travel={travel}>
        <div
          style={{
            fontFamily: fonts.display,
            fontSize: px(width, scale.beat * squeeze),
            fontWeight: 800,
            lineHeight: 1.04,
            color: colours.ink,
            overflowWrap: 'anywhere',
          }}
        >
          {beat.text}
        </div>
      </Settle>

      {beat.detail ? (
        <>
          <div style={{ height: px(width, 0.022) }} />
          <Wipe delay={8} width={px(width, 0.14)} height={px(width, scale.rule)} colour={accent} />
          <div style={{ height: px(width, 0.026) }} />
          <Settle delay={10} travel={travel}>
            <div
              style={{
                fontFamily: fonts.ui,
                fontSize: px(width, scale.detail * squeeze),
                fontWeight: 400,
                lineHeight: 1.3,
                color: colours.slate,
                overflowWrap: 'anywhere',
              }}
            >
              {beat.detail}
            </div>
          </Settle>
        </>
      ) : null}
    </Card>
  )
}

function Outro({ props, margin, inset, travel, squeeze, fonts }: CardProps & { props: ReelProps }) {
  const { width } = useVideoConfig()
  const frame = useCurrentFrame()
  const chartWidth = width - margin * 2
  const chartHeight = px(width, 0.26 * squeeze)

  return (
    <Card margin={margin} inset={inset}>
      <Settle travel={travel}>
        <div
          style={{
            fontFamily: fonts.ui,
            fontSize: px(width, scale.eyebrow),
            fontWeight: 600,
            color: colours.slate,
          }}
        >
          {props.regionName ? `Trending in ${props.regionName}` : 'Trending now'}
        </div>
      </Settle>

      <div style={{ height: px(width, 0.03) }} />

      {props.velocity.length > 1 ? (
        <Sparkline
          series={props.velocity}
          width={chartWidth}
          height={chartHeight}
          stroke={px(width, 0.012)}
          progress={interpolate(frame, [4, OUTRO_FRAMES * 0.7], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          })}
        />
      ) : null}

      <div style={{ height: px(width, 0.04) }} />

      <Settle delay={8} travel={travel}>
        <div
          style={{
            fontFamily: fonts.display,
            fontSize: px(width, scale.headline * 0.62 * squeeze),
            fontWeight: 700,
            lineHeight: 1.08,
            color: colours.ink,
            overflowWrap: 'anywhere',
          }}
        >
          {props.headline}
        </div>
      </Settle>
    </Card>
  )
}

/** Hashtags left, brand right, on every frame — the post templates' footer. */
function Footer({
  props,
  margin,
  fonts,
}: {
  props: ReelProps
  margin: number
  fonts: { display: string; ui: string }
}) {
  const { width, height } = useVideoConfig()
  const size = px(width, scale.footer)

  return (
    <div
      style={{
        position: 'absolute',
        left: margin,
        right: margin,
        // Clear of the safe area every platform crops into, and of the
        // caption and profile furniture a reel player draws over the bottom.
        bottom: px(height, 0.07),
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: px(width, 0.04),
        fontFamily: fonts.ui,
        fontSize: size,
        fontWeight: 600,
        color: colours.slate,
      }}
    >
      <span
        style={{
          overflow: 'hidden',
          whiteSpace: 'nowrap',
          textOverflow: 'ellipsis',
        }}
      >
        {props.hashtags.slice(0, 3).join(' ')}
      </span>
      <span style={{ color: colours.ink, whiteSpace: 'nowrap', fontWeight: 700 }}>
        {props.brandName}
      </span>
    </div>
  )
}

/**
 * The text column every card shares: left-aligned, centred inside the band
 * rather than inside the whole frame. See `band` in theme.ts for why.
 */
function Card({
  children,
  margin,
  inset,
}: {
  children: React.ReactNode
  margin: number
  inset: Inset
}) {
  const { height } = useVideoConfig()
  return (
    <AbsoluteFill
      style={{
        paddingLeft: margin,
        paddingRight: margin,
        paddingTop: Math.round(height * inset.top),
        paddingBottom: Math.round(height * inset.bottom),
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'flex-start',
      }}
    >
      {children}
    </AbsoluteFill>
  )
}
