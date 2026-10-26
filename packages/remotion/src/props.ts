/**
 * The props a composition renders from.
 *
 * This mirrors `VideoBrief.as_props()` in apps/api/app/video/base.py exactly.
 * The Python side is the only producer and it is in another language, so there
 * is no compiler to catch a rename on one side — a test there pins the key
 * names, and this file is the other half of that contract. Change one, change
 * both.
 */

export type BeatProps = {
  /** The line held on screen. */
  text: string
  /** Optional second line, set smaller underneath. */
  detail: string
  /** How long this beat holds. Frames, not seconds: seconds here would be
   *  re-derived against the fps and drift by a frame or two per beat. */
  frames: number
}

export type ReelProps = {
  headline: string
  beats: BeatProps[]
  brandName: string
  primaryColor: string
  secondaryColor: string
  logoUrl: string | null
  regionName: string
  hashtags: string[]
  /** Six points, matching the ladder row this topic came from. */
  velocity: number[]
  /** Unicode script name: "DEVANAGARI", "TAMIL", … or "LATIN". */
  script: string
  width: number
  height: number
  fps: number
  /** How long the opening card holds. Measured from its narration. */
  titleFrames: number
  /** How long the closing card holds. Measured from its narration. */
  outroFrames: number
  durationInFrames: number
}

/**
 * What the Remotion studio opens with, and what a render falls back to if a
 * field is missing. Real copy rather than lorem: placeholder text hides the
 * two things that actually break these layouts, which are long Indic words
 * and headlines that wrap once more than you expected.
 */
export const defaultProps: ReelProps = {
  headline: 'Goa unveils AI policy 2026 and launches a state-level hackathon',
  beats: [
    { text: 'Goa has an AI policy', detail: 'Announced this week', frames: 90 },
    { text: '₹2 crore in prizes', detail: 'For student teams', frames: 75 },
    { text: 'Applications close 30 November', detail: '', frames: 90 },
  ],
  brandName: 'BitnBin',
  primaryColor: '#1B2230',
  secondaryColor: '#D8322B',
  logoUrl: null,
  regionName: 'Goa',
  hashtags: ['#GoaAI', '#AIPolicy', '#Hackathon'],
  velocity: [10, 22, 18, 44, 61, 90],
  script: 'LATIN',
  width: 1080,
  height: 1920,
  fps: 30,
  titleFrames: 60,
  outroFrames: 45,
  durationInFrames: 360,
}

/**
 * Every key `VideoBrief.as_props()` sends.
 *
 * Checked at the door rather than defaulted silently. withDefaults() below
 * will happily substitute a value for a missing key, which is right for a bad
 * value and wrong for a missing one: if the Python side is renamed and this
 * file is not, a defaulted key renders a reel about the wrong topic and
 * nothing anywhere says so.
 */
export const REQUIRED_PROP_KEYS: readonly (keyof ReelProps)[] = [
  'headline',
  'beats',
  'brandName',
  'primaryColor',
  'secondaryColor',
  'logoUrl',
  'regionName',
  'hashtags',
  'velocity',
  'script',
  'width',
  'height',
  'fps',
  'titleFrames',
  'outroFrames',
  'durationInFrames',
]

/** Keys REQUIRED_PROP_KEYS expects that are not present. */
export function missingPropKeys(props: Record<string, unknown> | undefined): string[] {
  const given = props ?? {}
  return REQUIRED_PROP_KEYS.filter((key) => !(key in given))
}

/**
 * What the opening and closing cards hold for when nothing says otherwise.
 *
 * Once a reel is narrated these come from the props instead: the voice over
 * each card decides how long that card is, the same as a beat.
 */
export const DEFAULT_TITLE_FRAMES = 60
export const DEFAULT_OUTRO_FRAMES = 45

/**
 * Props arrive from another process, so every field is checked rather than
 * trusted. A missing colour is a black reel; a missing beats array is a crash
 * inside the composition, where the error message is a stack trace in a
 * headless Chromium log rather than anything a user could act on.
 */
export function withDefaults(raw: Partial<ReelProps> | undefined): ReelProps {
  const props = raw ?? {}
  const beats = Array.isArray(props.beats)
    ? props.beats
        .filter((b): b is BeatProps => Boolean(b) && typeof b.text === 'string')
        .map((b) => ({
          text: b.text,
          detail: typeof b.detail === 'string' ? b.detail : '',
          frames: Number.isFinite(b.frames) && b.frames > 0 ? Math.round(b.frames) : 60,
        }))
    : defaultProps.beats

  const fps = positive(props.fps, defaultProps.fps)
  const width = positive(props.width, defaultProps.width)
  const height = positive(props.height, defaultProps.height)
  const titleFrames = positive(props.titleFrames, DEFAULT_TITLE_FRAMES)
  const outroFrames = positive(props.outroFrames, DEFAULT_OUTRO_FRAMES)
  const beatFrames = beats.reduce((total, b) => total + b.frames, 0)

  return {
    headline: text(props.headline, defaultProps.headline),
    beats,
    brandName: text(props.brandName, defaultProps.brandName),
    primaryColor: colour(props.primaryColor, defaultProps.primaryColor),
    secondaryColor: colour(props.secondaryColor, defaultProps.secondaryColor),
    logoUrl: typeof props.logoUrl === 'string' && props.logoUrl ? props.logoUrl : null,
    regionName: typeof props.regionName === 'string' ? props.regionName : '',
    hashtags: Array.isArray(props.hashtags) ? props.hashtags.filter(isText).slice(0, 4) : [],
    velocity: Array.isArray(props.velocity) ? props.velocity.filter(Number.isFinite) : [],
    script: text(props.script, 'LATIN'),
    width,
    height,
    fps,
    titleFrames: Math.round(titleFrames),
    outroFrames: Math.round(outroFrames),
    // Derived rather than taken on trust: a durationInFrames shorter than the
    // cards silently truncates the last one, and a longer one holds a frozen
    // frame at the end. Both look like a broken render, and with a voiceover
    // underneath, both also put the audio out of step with the picture.
    durationInFrames: Math.round(titleFrames) + beatFrames + Math.round(outroFrames),
  }
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function text(value: unknown, fallback: string): string {
  return isText(value) ? value : fallback
}

function positive(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback
}

/** Hex only. An arbitrary string reaches CSS unescaped. */
function colour(value: unknown, fallback: string): string {
  return typeof value === 'string' && /^#[0-9a-f]{3,8}$/i.test(value.trim())
    ? value.trim()
    : fallback
}
