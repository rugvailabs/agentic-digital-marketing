'use client'

import { contrastingInk } from '@/lib/brand'

/**
 * The three post templates, drawn in CSS at thumbnail size.
 *
 * Not a render: the API draws these with Pillow, and asking it for three
 * PNGs on every keystroke would be both slow and a waste of a worker. This
 * is a promise about what the render will do, so every number here is the
 * same fraction of the canvas that `app/images/pillow.py` uses — margin
 * 0.08, poster headline 0.111, the colour block at 0.60, the footer rule at
 * `_footer_top`. Change one there and change it here, or the promise breaks.
 *
 * Everything is sized in `cqw` against a square container query, which is
 * what makes one set of fractions work at 180px and at 420px.
 */

export const TEMPLATES = ['poster', 'split', 'wire'] as const
export type Template = (typeof TEMPLATES)[number]

export const TEMPLATE_LABELS: Record<Template, string> = {
  poster: 'Poster',
  split: 'Split panel',
  wire: 'Wire',
}

/** What each one is for, shown under the thumbnail. */
export const TEMPLATE_NOTES: Record<Template, string> = {
  poster: 'For a statement',
  split: 'For a number',
  wire: 'For "this is moving"',
}

const PAPER = '#EEF1F6'
const INK = '#1B2230'
const SLATE = '#5B6578'
const RULE = '#D5DAE3'
const CHILLI = '#D8322B'

/** Sample copy. Fixed, so switching brand changes only the brand. */
const HEADLINE = 'India seal the series in Chennai'
const SUBLINE = 'Three wickets in the last over.'
const TOKEN = '3-0'
const HASHTAGS = '#INDvAUS #Chennai'
const VELOCITY = [10, 14, 22, 30, 61, 88]

export type PreviewBrand = {
  name: string
  logoUrl: string | null
  primaryColor: string
  secondaryColor: string
  fontChoice: string
}

export function TemplatePreview({ template, brand }: { template: Template; brand: PreviewBrand }) {
  return (
    <div
      // The container query the fractions below are measured against. Square,
      // like the "square" size the API renders first.
      style={{ containerType: 'inline-size' }}
      className="w-full"
      aria-label={`${TEMPLATE_LABELS[template]} template in ${brand.name || 'your brand'} colours`}
      role="img"
    >
      <div className="relative aspect-square w-full overflow-hidden border border-border">
        {template === 'poster' ? <Poster brand={brand} /> : null}
        {template === 'split' ? <Split brand={brand} /> : null}
        {template === 'wire' ? <Wire brand={brand} /> : null}
      </div>
    </div>
  )
}

/** The headline face, mirroring Brand.font_choice. */
const face = (brand: PreviewBrand) =>
  brand.fontChoice === 'ui' ? 'var(--font-ui)' : 'var(--font-display)'

function Poster({ brand }: { brand: PreviewBrand }) {
  const ink = contrastingInk(brand.primaryColor)
  return (
    <div className="absolute inset-0" style={{ backgroundColor: brand.primaryColor }}>
      <div className="absolute" style={{ left: '8cqw', right: '8cqw', top: '14cqw', color: ink }}>
        <p
          style={{
            fontFamily: face(brand),
            fontWeight: 800,
            fontSize: '11.1cqw',
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
          }}
        >
          {HEADLINE}
        </p>
        <div
          style={{
            marginTop: '3.4cqw',
            width: '16cqw',
            height: '0.9cqw',
            backgroundColor: brand.secondaryColor,
          }}
        />
        <p style={{ marginTop: '3.4cqw', fontSize: '3.8cqw', lineHeight: 1.35, opacity: 0.92 }}>
          {SUBLINE}
        </p>
      </div>
      <Footer brand={brand} ink={ink} rule={false} />
    </div>
  )
}

function Split({ brand }: { brand: PreviewBrand }) {
  const blockInk = contrastingInk(brand.secondaryColor)
  return (
    <div className="absolute inset-0" style={{ backgroundColor: '#FFFFFF' }}>
      <div
        className="absolute inset-x-0 top-0 flex items-center"
        style={{ height: '60%', backgroundColor: brand.secondaryColor, paddingLeft: '8cqw' }}
      >
        <span
          style={{
            fontFamily: face(brand),
            fontWeight: 800,
            fontSize: '34cqw',
            lineHeight: 0.9,
            letterSpacing: '-0.03em',
            color: blockInk,
          }}
        >
          {TOKEN}
        </span>
      </div>
      <div className="absolute" style={{ left: '8cqw', right: '8cqw', top: '66cqw' }}>
        <p
          style={{
            fontFamily: face(brand),
            fontWeight: 700,
            fontSize: '5.8cqw',
            lineHeight: 1.12,
            color: INK,
          }}
        >
          {HEADLINE}
        </p>
        <p style={{ marginTop: '1.6cqw', fontSize: '3.2cqw', lineHeight: 1.3, color: SLATE }}>
          {SUBLINE}
        </p>
      </div>
      <Footer brand={brand} ink={INK} rule />
    </div>
  )
}

function Wire({ brand }: { brand: PreviewBrand }) {
  return (
    <div className="absolute inset-0" style={{ backgroundColor: PAPER }}>
      <div className="absolute" style={{ left: '8cqw', right: '8cqw', top: '10cqw' }}>
        <p style={{ fontSize: '2.9cqw', fontWeight: 600, color: SLATE }}>Trending in Tamil Nadu</p>
        <div
          style={{
            marginTop: '2.2cqw',
            height: 0,
            borderTop: `1px dotted ${RULE}`,
          }}
        />
        <p
          style={{
            marginTop: '4.5cqw',
            fontFamily: face(brand),
            fontWeight: 800,
            fontSize: '8.5cqw',
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
            color: INK,
          }}
        >
          {HEADLINE}
        </p>
        <p style={{ marginTop: '1.4cqw', fontSize: '3.2cqw', lineHeight: 1.3, color: SLATE }}>
          {SUBLINE}
        </p>
      </div>
      {/* The point of this template, so it gets the room the renderer gives it. */}
      <svg
        className="absolute"
        style={{ left: '8cqw', right: '8cqw', top: '60%', height: '20%', width: '84%' }}
        viewBox="0 0 100 30"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <polyline
          points={VELOCITY.map(
            (v, i) => `${(i / (VELOCITY.length - 1)) * 100},${30 - (v / 88) * 29}`,
          ).join(' ')}
          fill="none"
          stroke={CHILLI}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <Footer brand={brand} ink={INK} rule dotted />
    </div>
  )
}

/**
 * Hashtags left, logo or wordmark right — and the wordmark goes when a logo
 * arrives, exactly as the renderer does it.
 */
function Footer({
  brand,
  ink,
  rule,
  dotted = false,
}: {
  brand: PreviewBrand
  ink: string
  rule: boolean
  dotted?: boolean
}) {
  return (
    <div className="absolute" style={{ left: '8cqw', right: '8cqw', bottom: '5.5cqw' }}>
      {rule ? (
        <div
          style={{
            marginBottom: '3cqw',
            height: 0,
            borderTop: dotted ? `1px dotted ${RULE}` : `1px solid ${ink}`,
          }}
        />
      ) : null}
      <div className="flex items-end justify-between" style={{ gap: '4cqw' }}>
        <span
          style={{
            fontSize: '2.9cqw',
            fontWeight: 600,
            color: ink,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {HASHTAGS}
        </span>
        {brand.logoUrl ? (
          /* A blob: URL from the file picker, which next/image cannot take. */
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={brand.logoUrl}
            alt=""
            style={{ height: '5.5cqw', maxWidth: '30cqw', objectFit: 'contain' }}
          />
        ) : (
          <span style={{ fontSize: '2.9cqw', fontWeight: 700, color: ink, whiteSpace: 'nowrap' }}>
            {brand.name || 'Your brand'}
          </span>
        )}
      </div>
    </div>
  )
}
