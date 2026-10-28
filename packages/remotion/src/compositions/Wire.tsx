/**
 * The wire desk in motion.
 *
 * Paper ground with a little tooth, ink type, one chilli accent, the same two
 * faces and the same left-aligned column as the board. If a frame were
 * printed it would be a post.
 *
 * Three layers, in order of permanence:
 *
 *   Paper     the ground, with its grain tiled into the background. Under
 *             everything, not over it — see texture.ts for what a blended
 *             layer on top cost.
 *   Chrome    the edition line, the masthead and the footer. On every frame,
 *             so the reel always says where it came from and how far through
 *             it is.
 *   Cards     the title, one per beat, and the close. Each enters and leaves.
 *
 * Type is measured, never sized by a fixed fraction: a three-word beat is set
 * enormous and a long one steps down and wraps. That is where the scale
 * contrast comes from, and it is why a different topic does not need a
 * different layout.
 */

import { useMemo } from 'react'
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion'

import { Captions } from '../components/Captions'
import { Reveal, Wipe, outCubic } from '../components/Reveal'
import { Sparkline } from '../components/Sparkline'
import { Ticker } from '../components/Ticker'
import { type Families, useFonts } from '../fonts'
import { type BeatProps, type ReelProps, withDefaults } from '../props'
import { grainUrl } from '../texture'
import { type Format, colours, formatFor, leading, motion, px } from '../theme'
import { fitLines } from '../typography'

type Band = { top: number; height: number }

export const Wire: React.FC<ReelProps> = (raw) => {
  // Guarded rather than trusted: these arrive from another process, and a
  // missing beats array is a stack trace in a headless Chromium log rather
  // than anything a user could act on.
  const props = withDefaults(raw)
  const { width, height } = useVideoConfig()
  const fonts = useFonts(props.script)
  const format = formatFor(width, height)

  const segments = [props.titleFrames, ...props.beats.map((b) => b.frames), props.outroFrames]
  const outroStart = segments.slice(0, -1).reduce((total, f) => total + f, 0)

  const margin = px(width, format.margin)
  const measure = px(width, format.measure)
  const travel = px(width, motion.travel)
  const band: Band = {
    top: Math.round(height * format.band.top),
    height: Math.round(height * (1 - format.band.top - format.band.bottom)),
  }

  let cursor = props.titleFrames

  // Nothing is drawn until the faces are in: the layout is decided by
  // measuring text, and measuring against a fallback builds a layout for a
  // font that is not the one it renders in. Capture is held by delayRender
  // until this flips, so no frame is ever taken of the bare ground.
  if (!fonts.ready) {
    return <AbsoluteFill style={{ backgroundColor: colours.paper }} />
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colours.paper,
        backgroundImage: grainUrl,
        backgroundRepeat: 'repeat',
        fontKerning: 'normal',
      }}
    >
      <Chrome props={props} format={format} fonts={fonts} segments={segments} />

      <Sequence durationInFrames={props.titleFrames} name="Title" layout="none">
        <Card band={band} margin={margin}>
          <Title
            props={props}
            format={format}
            fonts={fonts}
            measure={measure}
            band={band}
            travel={travel}
            cardFrames={props.titleFrames}
          />
        </Card>
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
            layout="none"
          >
            <Card band={band} margin={margin}>
              <BeatCard
                beat={beat}
                format={format}
                fonts={fonts}
                measure={measure}
                band={band}
                travel={travel}
                accent={props.secondaryColor}
                cardFrames={beat.frames}
              />
            </Card>
          </Sequence>
        )
      })}

      <Sequence from={outroStart} durationInFrames={props.outroFrames} name="Outro" layout="none">
        <Card band={band} margin={margin}>
          <Outro
            props={props}
            format={format}
            fonts={fonts}
            measure={measure}
            band={band}
            travel={travel}
            cardFrames={props.outroFrames}
          />
        </Card>
      </Sequence>
      {/* Over the cards, under nothing. A caption that a beat can cover is
          not a caption. */}
      <Captions
        captions={props.captions}
        format={format}
        fonts={fonts}
        accent={props.secondaryColor}
      />
    </AbsoluteFill>
  )
}

/**
 * The furniture: edition line, masthead, footer.
 *
 * It settles once, at the top of the reel, and then holds. Re-animating it
 * per card would make the frame twitch on every edit — the same reason the
 * ladder animates once on load and not on every selection.
 */
function Chrome({
  props,
  format,
  fonts,
  segments,
}: {
  props: ReelProps
  format: Format
  fonts: Families
  segments: number[]
}) {
  const { width, height } = useVideoConfig()
  const frame = useCurrentFrame()
  const margin = px(width, format.margin)
  const travel = px(width, motion.travel)

  const outroStart = segments.slice(0, -1).reduce((total, f) => total + f, 0)
  // The closing card makes the chart the subject. Two of them on screen at
  // once is the same thing said twice, so the small one steps aside for it.
  const markOpacity = interpolate(frame, [outroStart - 8, outroStart], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  })

  const label = props.regionName ? `Trending in ${props.regionName}` : 'Trending now'

  return (
    <>
      <div
        style={{
          position: 'absolute',
          top: Math.round(height * format.ticker),
          left: margin,
          right: margin,
        }}
      >
        <Reveal travel={travel}>
          <Ticker
            segments={segments}
            height={Math.max(3, px(width, 0.006))}
            gap={px(width, 0.008)}
          />
        </Reveal>
      </div>

      <div
        style={{
          position: 'absolute',
          top: Math.round(height * format.masthead),
          left: margin,
          right: margin,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: px(width, 0.04),
        }}
      >
        <Reveal delay={3} travel={travel}>
          <span
            style={{
              fontFamily: fonts.ui,
              fontSize: px(width, format.label),
              fontWeight: 600,
              color: colours.slate,
              letterSpacing: '0.005em',
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </span>
        </Reveal>

        {props.velocity.length > 1 ? (
          <div style={{ opacity: markOpacity, lineHeight: 0 }}>
            <Reveal delay={6} travel={travel}>
              <Sparkline
                series={props.velocity}
                width={px(width, 0.17)}
                height={px(width, 0.05)}
                stroke={Math.max(2, px(width, 0.005))}
                progress={interpolate(frame, [6, 26], [0, 1], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                })}
              />
            </Reveal>
          </div>
        ) : null}
      </div>

      <Footer props={props} format={format} fonts={fonts} />
    </>
  )
}

/** Hashtags left, brand right — the post templates' footer, on every frame. */
function Footer({ props, format, fonts }: { props: ReelProps; format: Format; fonts: Families }) {
  const { width, height } = useVideoConfig()
  const frame = useCurrentFrame()
  const margin = px(width, format.margin)

  // A hairline above it, wiped in once. It is what separates the footer from
  // the card, rather than a gap doing the work — the board groups by rules
  // and spacing for the same reason.
  const ruleWidth = interpolate(frame, [4, 4 + motion.wipe * 1.6], [0, width - margin * 2], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: outCubic,
  })

  return (
    <div
      style={{
        position: 'absolute',
        left: margin,
        right: margin,
        bottom: Math.round(height * format.footerBottom),
        display: 'flex',
        flexDirection: 'column',
        gap: px(width, 0.022),
      }}
    >
      <div
        style={{
          width: ruleWidth,
          height: Math.max(1, px(width, 0.0015)),
          backgroundColor: colours.rule,
        }}
      />
      <Reveal delay={5} travel={px(width, motion.travel)}>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            gap: px(width, 0.04),
            fontFamily: fonts.ui,
            fontSize: px(width, format.footer),
            fontWeight: 600,
            color: colours.slate,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          <span style={{ overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
            {props.hashtags.slice(0, 3).join(' ')}
          </span>
          {props.logoUrl ? (
            /*
             * The logo replaces the wordmark rather than sitting beside it,
             * exactly as the still templates do — two marks for one brand in
             * a 30px footer is clutter. `height` is set and `width` left to
             * the aspect ratio, capped so a wide wordmark cannot reach the
             * hashtags.
             */
            <Img
              src={props.logoUrl}
              alt={props.brandName}
              style={{
                height: px(width, 0.055),
                maxWidth: px(width, 0.3),
                objectFit: 'contain',
                objectPosition: 'right bottom',
              }}
            />
          ) : (
            <span style={{ color: colours.ink, whiteSpace: 'nowrap', fontWeight: 700 }}>
              {props.brandName}
            </span>
          )}
        </div>
      </Reveal>
    </div>
  )
}

/**
 * The text column every card shares.
 *
 * Centred inside the band, not inside the frame. The band is what keeps the
 * block clear of the caption and account row a reel player draws over the
 * bottom; centring within it is what stops a short card pooling all its white
 * space at the top. Anchoring to the band's baseline instead held the
 * baseline steady, which sounds better than it looks: "Gold is up" at 200px
 * sat in the bottom third with half the frame empty above it.
 */
function Card({
  children,
  band,
  margin,
}: {
  children: React.ReactNode
  band: Band
  margin: number
}) {
  return (
    <div
      style={{
        position: 'absolute',
        top: band.top,
        height: band.height,
        left: margin,
        right: margin,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'flex-start',
      }}
    >
      {children}
    </div>
  )
}

/* ── cards ───────────────────────────────────────────────────────────── */

type CardShared = {
  format: Format
  fonts: Families
  measure: number
  band: Band
  travel: number
}

/** A measured block, one Reveal per line so the type arrives as a sweep. */
function Lines({
  fitted,
  fontFamily,
  fontWeight,
  colour,
  travel,
  cardFrames,
  delay = 0,
}: {
  fitted: { lines: string[]; fontSize: number; lineHeight: number }
  fontFamily: string
  fontWeight: number
  colour: string
  travel: number
  cardFrames?: number
  delay?: number
}) {
  return (
    <div>
      {fitted.lines.map((line, index) => (
        <Reveal
          key={index}
          delay={delay + index * motion.stagger}
          travel={travel}
          cardFrames={cardFrames}
        >
          <div
            style={{
              fontFamily,
              fontWeight,
              fontSize: fitted.fontSize,
              lineHeight: `${fitted.lineHeight}px`,
              color: colour,
              letterSpacing: '-0.015em',
              // Long Tamil and Telugu words cannot be broken at a space, and
              // a word running off the canvas is worse than a hyphen.
              overflowWrap: 'anywhere',
            }}
          >
            {line}
          </div>
        </Reveal>
      ))}
    </div>
  )
}

function Title({
  props,
  format,
  fonts,
  measure,
  band,
  travel,
  cardFrames,
}: CardShared & { props: ReelProps; cardFrames: number }) {
  const { width } = useVideoConfig()
  const ruleHeight = Math.max(3, px(width, 0.005))
  const gap = px(width, 0.035)

  const fitted = useMemo(
    () =>
      fitLines({
        text: props.headline,
        maxWidth: measure,
        // The rule and the gap come out of the band before the type is sized, so
        // a long headline shrinks rather than pushing the rule off the top.
        maxHeight: band.height - ruleHeight - gap,
        maxFontSize: px(width, format.headline.max),
        minFontSize: px(width, format.headline.min),
        fontFamily: fonts.display,
        fontWeight: 800,
        leading: fonts.indic ? leading.indic : leading.latin,
        maxLines: format.maxLines,
      }),
    [props.headline, measure, band.height, ruleHeight, gap, width, format, fonts],
  )

  return (
    <>
      {/* The rule sits above the headline here and below the line on a beat
          card. That is how the opening reads as the opening without a label
          saying so. */}
      <Wipe
        width={px(width, 0.22)}
        height={ruleHeight}
        colour={colours.chilli}
        cardFrames={cardFrames}
      />
      <div style={{ height: gap }} />
      <Lines
        fitted={fitted}
        fontFamily={fonts.display}
        fontWeight={800}
        colour={colours.ink}
        travel={travel}
        cardFrames={cardFrames}
        delay={3}
      />
    </>
  )
}

function BeatCard({
  beat,
  format,
  fonts,
  measure,
  band,
  travel,
  accent,
  cardFrames,
}: CardShared & { beat: BeatProps; accent: string; cardFrames: number }) {
  const { width } = useVideoConfig()
  const detailSize = px(width, format.detail)
  const ruleHeight = Math.max(3, px(width, 0.005))
  const gap = px(width, 0.026)

  // The detail's rows are reserved before the beat is sized. Sized against
  // the whole band, a beat that takes one line more than expected pushes the
  // detail through the footer — which is exactly what happened to the Split
  // post template when the Latin face changed.
  const detailHeight = beat.detail ? Math.round(detailSize * 1.3) + ruleHeight + gap * 2 : 0

  const fitted = useMemo(
    () =>
      fitLines({
        text: beat.text,
        maxWidth: measure,
        maxHeight: band.height - detailHeight,
        maxFontSize: px(width, format.beat.max),
        minFontSize: px(width, format.beat.min),
        fontFamily: fonts.display,
        fontWeight: 800,
        leading: fonts.indic ? leading.indic : leading.latin,
        maxLines: format.maxLines,
      }),
    [beat.text, measure, band.height, detailHeight, width, format, fonts],
  )

  const after = motion.stagger * fitted.lines.length

  return (
    <>
      <Lines
        fitted={fitted}
        fontFamily={fonts.display}
        fontWeight={800}
        colour={colours.ink}
        travel={travel}
        cardFrames={cardFrames}
      />
      {beat.detail ? (
        <>
          <div style={{ height: gap }} />
          <Wipe
            delay={after}
            width={px(width, 0.16)}
            height={ruleHeight}
            colour={accent}
            cardFrames={cardFrames}
          />
          <div style={{ height: gap }} />
          <Reveal delay={after + 3} travel={travel} cardFrames={cardFrames}>
            <div
              style={{
                fontFamily: fonts.ui,
                fontSize: detailSize,
                fontWeight: 400,
                lineHeight: 1.3,
                color: colours.slate,
                maxWidth: measure,
                overflowWrap: 'anywhere',
              }}
            >
              {beat.detail}
            </div>
          </Reveal>
        </>
      ) : null}
    </>
  )
}

/**
 * The close: the chart large, then the headline under it.
 *
 * The chart is the subject here rather than a mark, so it takes the full
 * column and its end dot lands with a spring once the line has drawn. The
 * headline is set smaller than on the title card — it is a reminder, not the
 * opening statement, and giving it the same size would make the close read as
 * a repeat of the open.
 */
function Outro({
  props,
  format,
  fonts,
  measure,
  band,
  travel,
  cardFrames,
}: CardShared & { props: ReelProps; cardFrames: number }) {
  const { width } = useVideoConfig()
  const frame = useCurrentFrame()
  const hasChart = props.velocity.length > 1
  const chartHeight = hasChart ? px(width, format.chart) : 0
  const gap = px(width, 0.04)
  // Half way through the close, not at the end: the line has to finish
  // drawing and the dot has to land with time left to be seen.
  const dotAt = Math.round(cardFrames * 0.5)

  const fitted = useMemo(
    () =>
      fitLines({
        text: props.headline,
        maxWidth: measure,
        maxHeight: band.height - chartHeight - gap,
        maxFontSize: px(width, format.headline.max * 0.66),
        minFontSize: px(width, format.headline.min),
        fontFamily: fonts.display,
        fontWeight: 700,
        leading: fonts.indic ? leading.indic : leading.latin,
        maxLines: format.maxLines,
      }),
    [props.headline, measure, band.height, chartHeight, gap, width, format, fonts],
  )

  return (
    <>
      {hasChart ? (
        <>
          <div style={{ lineHeight: 0 }}>
            <Sparkline
              series={props.velocity}
              width={measure}
              height={chartHeight}
              stroke={px(width, 0.013)}
              progress={interpolate(frame, [3, dotAt], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: outCubic,
              })}
              dotAt={dotAt}
            />
          </div>
          {/* A baseline for the chart to sit on. Without it the line floats
              in the middle of the frame with nothing to read it against —
              the ladder gives its sparklines a row to sit in, and this is
              the equivalent. Drawn with the line, not before it. */}
          <Wipe
            delay={3}
            width={measure}
            height={Math.max(1, px(width, 0.0015))}
            colour={colours.rule}
            frames={dotAt}
          />
          <div style={{ height: gap }} />
        </>
      ) : null}
      <Lines
        fitted={fitted}
        fontFamily={fonts.display}
        fontWeight={700}
        colour={colours.ink}
        travel={travel}
        delay={6}
      />
    </>
  )
}
