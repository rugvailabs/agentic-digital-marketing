'use client'

import type { ContentAsset, ContentJob } from '@trendforge/types'

import { AssetCard } from '@/components/desk/AssetCard'
import { EmptyState } from '@/components/Empty'
import { SectionLabel, cx } from '@/components/house'

/**
 * The reel: what it will say, and the file once it exists.
 *
 * A reel takes minutes rather than seconds, so the waiting state carries
 * more weight here than it does for a post. The script appears as soon as
 * it is written — well before the video — which means there is something
 * to read and correct while the frames render, instead of a spinner.
 *
 * The brand, language and render controls live in Studio, which owns the
 * job. This renders what came back.
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

export function Reel({ job, busy }: { job: ContentJob | null; busy: boolean }) {
  const script = job?.assets.find((a) => a.kind === 'script')
  const video = job?.assets.find((a) => a.kind === 'video')
  const meta = (script?.meta_json ?? {}) as ScriptMeta
  const segments = meta.segments ?? []

  return (
    <div className="flex flex-col gap-4">
      {busy && !video ? (
        // Said once, plainly. A reel narrates, renders every frame through
        // a browser and then mixes; without this the first run looks stuck.
        <p className="text-sm text-slate">
          Narrating, then rendering every frame. This takes a few minutes — the script below appears
          as soon as it is written.
        </p>
      ) : null}

      {video?.url ? <VideoCard asset={video} jobId={job?.id} /> : null}

      {segments.length > 0 ? (
        <Script segments={segments} derived={meta.derived === true} spoken={!video} />
      ) : null}

      {!job && !busy ? (
        <EmptyState
          art="grid"
          title="No reel for this topic yet."
          hint="A narrated vertical video, in the language above. It takes a few minutes."
        />
      ) : null}
    </div>
  )
}

/**
 * The finished file, as a card with the same actions as a post image.
 *
 * Its own controls rather than the shared poster treatment: a reel is the
 * one asset you watch rather than look at, so the player stays and the
 * actions sit under it.
 */
function VideoCard({ asset, jobId }: { asset: ContentAsset; jobId?: number }) {
  const meta = (asset.meta_json ?? {}) as VideoMeta
  const width = Number(meta.width) || 1080
  const height = Number(meta.height) || 1920
  const seconds = Number(meta.duration_seconds) || 0

  return (
    <div className="max-w-[270px]">
      <AssetCard
        url={asset.url}
        jobId={jobId}
        title={meta.label || 'Reel'}
        subtitle={`${width}x${height}${seconds ? `, ${seconds.toFixed(1)}s` : ''}`}
      >
        <video
          src={asset.url ?? undefined}
          // Without this the player shows a blank sheet of paper until
          // someone presses play — frame zero is the opening card still
          // settling, which reads as a failed render.
          poster={meta.poster_url ?? undefined}
          controls
          playsInline
          preload="metadata"
          width={width}
          height={height}
          aria-label={meta.alt_text || 'Rendered reel'}
          className="block h-auto w-full"
        />
      </AssetCard>
      <p className="mt-1 text-xs text-faint">
        {meta.voice ? `Voice ${meta.voice}` : 'No voice recorded'}
        {meta.has_music ? ', music' : ''}
      </p>
    </div>
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
                  segment.text && 'border-l border-border pl-2.5',
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
