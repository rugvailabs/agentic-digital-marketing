'use client'

import type { Platform, SourceName, Trend } from '@trendforge/types'
import { SOURCE_LABELS } from '@trendforge/types'
import { useEffect, useRef, useState } from 'react'

import { SectionLabel, cx } from '@/components/house'

/** How long "Copied" stays before the button says what it does again. */
const COPIED_MS = 1600

/**
 * Hashtags grouped by platform, each group copyable on its own.
 *
 * Grouped rather than pooled because the tags genuinely differ: #AskIndia
 * means nothing on Instagram and #cricketreels means nothing in a YouTube
 * description, so one merged list is wrong everywhere it is pasted. A copy
 * button per group is the whole point — you are posting to one platform at a
 * time, and what you want on the clipboard is that platform's set.
 *
 * The topic's own tags come first, unlabelled by platform, because they are
 * the curator's handles for the story itself and work anywhere.
 */
export function Hashtags({
  trend,
  platforms,
}: {
  trend: Trend
  /** Every platform, so a configured one with no row can say why. */
  platforms: Platform[]
}) {
  const groups = trend.platforms
    .filter((row) => row.hashtags.length > 0)
    .map((row) => ({
      key: row.platform as SourceName,
      label: SOURCE_LABELS[row.platform as SourceName] ?? row.platform,
      tags: row.hashtags,
    }))

  // Instagram is measured on demand, when a topic is opened — its weekly
  // allowance is 30 unique hashtags, so measuring a whole board would spend
  // two thirds of a week in one cycle. Until then it has no row, and saying
  // so is more honest than leaving a gap that reads as "no tags here".
  const instagramConfigured = platforms.some((p) => p.name === 'instagram' && p.configured)
  const instagramMeasured = trend.platforms.some((row) => row.platform === 'instagram')
  const showInstagramPending = instagramConfigured && !instagramMeasured

  if (trend.hashtags.length === 0 && groups.length === 0 && !showInstagramPending) return null

  return (
    // The heading lives here, not in the Desk, because this is the only
    // place that knows whether there is anything under it. With it outside,
    // a topic with no tags rendered "Hashtags" over empty space.
    <div>
      <SectionLabel>Hashtags</SectionLabel>
      <div className="mt-2 flex flex-col">
        {trend.hashtags.length > 0 ? <Group label="Topic" tags={trend.hashtags} emphasis /> : null}

        {groups.map((group) => (
          <Group key={group.key} label={group.label} tags={group.tags} />
        ))}

        {showInstagramPending ? (
          <div className="flex items-baseline gap-4 border-t border-dotted border-rule py-2.5">
            <span className="w-24 shrink-0 text-xs text-slate">Instagram</span>
            <span className="text-sm text-slate">Not measured yet</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function Group({
  label,
  tags,
  emphasis = false,
}: {
  label: string
  tags: string[]
  /** The topic's own tags, set in ink rather than slate. */
  emphasis?: boolean
}) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Clearing on unmount: switching topics unmounts these mid-timeout, and a
  // setState afterwards is a leak warning in dev and nothing useful anywhere.
  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    const text = tags.join(' ')
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Clipboard access is refused on an insecure origin and by some
      // policies. Silently doing nothing would look like the button is
      // broken, so say it did not work rather than claiming it did.
      setCopied(false)
      window.prompt('Copy these hashtags', text)
      return
    }
    setCopied(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), COPIED_MS)
  }

  return (
    <div className="flex items-baseline gap-4 border-t border-dotted border-rule py-2.5">
      <span className="w-24 shrink-0 text-xs text-slate">{label}</span>
      <p
        className={cx(
          'flex min-w-0 flex-1 flex-wrap gap-x-3 gap-y-1 text-sm',
          emphasis ? 'font-medium text-ink' : 'text-ink',
        )}
      >
        {tags.map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </p>
      <button
        type="button"
        onClick={copy}
        // Says what will happen, per CLAUDE.md, and names the group so the
        // accessible label is not eight identical "Copy" buttons.
        aria-label={`Copy ${label} hashtags`}
        className="shrink-0 self-start text-xs text-slate hover:text-ink"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}
