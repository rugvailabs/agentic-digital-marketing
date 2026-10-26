'use client'

import type { ContentAsset, ContentJob } from '@trendforge/types'

import { SectionLabel, cx } from '@/components/primitives'
import { statusLabel } from '@/lib/jobs'

/**
 * The reel: what it will say, and the file once it exists.
 *
 * A reel takes minutes rather than seconds, so the waiting state carries more
 * weight here than it does for a post. The script appears as soon as it is
 * written — well before the video — which means there is something to read
 * and correct while the frames render, instead of a spinner.
 */

type ScriptSegment = {
  kind: string
  say: string
  text: string
  detail: string
}

type ScriptMeta = {
  headline?: string
  segments?: ScriptSegment[]
  derived?: boolean
  alt_text?: string
}

type VideoMeta = {
  width?: number
  height?: number
  duration_seconds?: number
  audio_codec?: string
  has_music?: boolean
  voice?: string
  label?: string
  alt_text?: string
  poster_url?: string | null
}

export function Reel({
  job,
  busy,
  error,
  onRender,
  blocked,
  disabled,
}: {
  job: ContentJob | null
  busy: boolean
  error: string | null
  onRender: () => void
  blocked: boolean
  disabled: boolean
}) {
  const script = job?.assets.find((a) => a.kind === 'script')
  const video = job?.assets.find((a) => a.kind === 'video')
  const meta = (script?.meta_json ?? {}) as ScriptMeta
  const segments = meta.segments ?? []

  return (
    <div className="mt-8 flex flex-col gap-3 border-t border-rule pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel>Reel</SectionLabel>
        {job ? (
          <span className="num text-xs text-slate">{statusLabel('reel', job.status)}</span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRender}
          disabled={busy || blocked || disabled}
          className="border border-ink px-3 py-1.5 text-sm text-ink transition-colors hover:bg-row-hover disabled:border-rule disabled:text-slate"
        >
          {busy ? 'Rendering' : video ? 'Render again' : 'Render reel'}
        </button>
        {busy ? (
          // Said once, plainly. A reel narrates, renders every frame through
          // a browser and then mixes; without this the first run looks stuck.
          <span className="text-xs text-slate">
            Narrating, then rendering every frame. A few minutes.
          </span>
        ) : null}
      </div>

      {blocked ? (
        <p className="text-sm text-slate">
          This topic is flagged as one we do not market against, so reels are off for it.
        </p>
      ) : null}

      {error || job?.error ? (
        <div className="mt-1 border-t border-rule pt-3">
          <p className="text-sm text-ink">{job?.error ?? error}</p>
          <button
            type="button"
            onClick={onRender}
            className="mt-2 border border-ink px-3 py-1 text-sm text-ink hover:bg-row-hover"
          >
            Try again
          </button>
        </div>
      ) : null}

      {video?.url ? <VideoCard asset={video} /> : null}

      {segments.length > 0 ? (
        <Script segments={segments} derived={meta.derived === true} spoken={!video} />
      ) : null}

      {!job && !error && !blocked ? (
        <p className="text-sm text-slate">
          Render a narrated vertical video for this topic, in the language above.
        </p>
      ) : null}
    </div>
  )
}

/**
 * The finished file.
 *
 * A border means "a rendered asset lives here" — the same card the post
 * images get, and the only thing in the app that gets one.
 */
function VideoCard({ asset }: { asset: ContentAsset }) {
  const meta = (asset.meta_json ?? {}) as VideoMeta
  const width = Number(meta.width) || 1080
  const height = Number(meta.height) || 1920
  const seconds = Number(meta.duration_seconds) || 0

  return (
    <figure className="mt-2 flex flex-col gap-2 self-start border border-rule bg-surface p-3">
      <video
        src={asset.url ?? undefined}
        // Without this the player shows a blank sheet of paper until someone
        // presses play — frame zero is the opening card still settling, which
        // reads as a failed render.
        poster={meta.poster_url ?? undefined}
        controls
        playsInline
        preload="metadata"
        width={width}
        height={height}
        aria-label={meta.alt_text || 'Rendered reel'}
        // Intrinsic size on the element so a 9:16 file holds its shape, and a
        // cap so it does not take the whole Desk.
        className="h-auto w-full max-w-[270px]"
      />
      <figcaption className="flex max-w-[270px] flex-col gap-0.5">
        <span className="text-xs text-ink">{meta.label || 'Reel'}</span>
        <span className="num text-xs text-slate">
          {width}×{height}
          {seconds ? ` · ${seconds.toFixed(1)}s` : ''}
        </span>
        <span className="text-xs text-slate">
          {meta.voice ? `Voice ${meta.voice}` : 'No voice recorded'}
          {meta.has_music ? ' · music' : ''}
        </span>
        {asset.url ? (
          <a
            href={asset.url}
            download
            className="mt-0.5 self-start text-xs text-ink underline decoration-rule underline-offset-2 hover:decoration-ink"
          >
            Save MP4
          </a>
        ) : null}
      </figcaption>
    </figure>
  )
}

/**
 * What the reel says, card by card.
 *
 * Two columns because there are two halves: what is on the card, and what the
 * voice says over it. They are deliberately different — the card carries
 * "2 crore", the voice carries "two crore rupees" — and seeing them side by
 * side is the only way to check they still agree.
 */
function Script({
  segments,
  derived,
  spoken,
}: {
  segments: ScriptSegment[]
  derived: boolean
  /** True while the video is still rendering, so the heading says why. */
  spoken: boolean
}) {
  return (
    <div className="mt-3 flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel>{spoken ? 'Script, while the frames render' : 'Script'}</SectionLabel>
        {derived ? (
          // Honest rather than flattering: this one came from the topic, not
          // from the writer, and it reads like it.
          <span className="text-xs text-slate">Built from the topic, not written</span>
        ) : null}
      </div>

      <ol className="flex flex-col">
        {segments.map((segment, index) => (
          <li
            key={index}
            className="rule-dotted grid grid-cols-[4.5rem_1fr] items-baseline gap-x-3 py-2"
          >
            <span className="text-xs text-slate">{cardName(segment.kind, index, segments)}</span>
            <span className="flex min-w-0 flex-col gap-1">
              {segment.text ? (
                <span className="text-sm font-medium text-ink">{segment.text}</span>
              ) : null}
              {segment.detail ? <span className="text-xs text-slate">{segment.detail}</span> : null}
              <span
                className={cx(
                  'text-sm text-slate',
                  // The spoken line is the one that is heard, so it keeps its
                  // own measure rather than being squeezed next to the card.
                  segment.text && 'border-l border-rule pl-2.5',
                )}
              >
                {segment.say}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** "Open", "Beat 1", "Close" — a position, not a type name. */
function cardName(kind: string, index: number, all: ScriptSegment[]): string {
  if (kind === 'title') return 'Open'
  if (kind === 'outro') return 'Close'
  const beats = all.filter((s) => s.kind === 'beat')
  const position = beats.indexOf(all[index] as ScriptSegment) + 1
  return `Beat ${position}`
}
