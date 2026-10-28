'use client'

import type { Platform } from '@trendforge/types'
import { SOURCE_LABELS, SOURCE_MARKS, SOURCE_NAMES, type SourceName } from '@trendforge/types'
import { useRouter } from 'next/navigation'
import { useCallback, useMemo } from 'react'

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/**
 * One segmented control, sized to the 440px wire column.
 *
 * The old strip was seven full labels — All, Trends, News, X, YouTube,
 * Reddit, Instagram — plus a "Connect 2" link, which needed about 600px and
 * got 440. It clipped mid-word ("Inst") and scrolled sideways with no
 * visible end, so three of the six platforms were effectively invisible.
 *
 * The fix is the two-letter marks the ladder rows already use. GT, GN, YT,
 * RD, X, IG are the house abbreviation for a platform, so the control reads
 * as the same language as the rows it filters, and seven segments fit with
 * room left. The full name is on the tooltip and in the accessible name, so
 * nothing is lost to anyone who needs the word.
 *
 * An unconfigured platform stays in the control, disabled, with a tooltip
 * saying where to connect it. Hiding it would read as a platform that does
 * not exist, when what is true is that nobody has pasted a key yet — and a
 * disabled segment with no explanation reads as a bug, which is why the
 * tooltip opens with no delay.
 */
export function PlatformFilter({
  platforms,
  available,
  region,
  selected,
}: {
  /** Every platform, configured or not, from GET /platforms. */
  platforms: Platform[]
  /** Those that are configured *and* cover the current region. */
  available: SourceName[]
  /** Current region code, preserved when the filter changes. */
  region: string
  /** The active `?platform=`, or undefined for All. */
  selected?: SourceName
}) {
  const router = useRouter()

  // Pipeline order from the types package, not the order the API answered
  // in: discovery sources first, then the places you post.
  const ordered = useMemo(() => {
    const known = new Map(platforms.map((p) => [p.name as SourceName, p]))
    return SOURCE_NAMES.filter((name) => known.has(name)).map((name) => known.get(name)!)
  }, [platforms])

  const go = useCallback(
    (platform?: SourceName) => {
      const query = new URLSearchParams({ region })
      if (platform) query.set('platform', platform)
      router.push(`/board?${query}`, { scroll: false })
    },
    [region, router],
  )

  return (
    <div className="border-b border-border px-3 py-2">
      <ToggleGroup
        type="single"
        value={selected ?? 'all'}
        // No empty value: deselecting the active segment should mean "All"
        // rather than "no filter chosen", which renders an empty ladder.
        onValueChange={(value) => go(value && value !== 'all' ? (value as SourceName) : undefined)}
        variant="outline"
        size="sm"
        className="w-full"
        aria-label="Filter by platform"
      >
        <ToggleGroupItem value="all" aria-label="All platforms" className="flex-1 px-2 text-xs">
          All
        </ToggleGroupItem>

        {ordered.map((platform) => {
          const name = platform.name as SourceName
          const label = SOURCE_LABELS[name] ?? name
          const usable = available.includes(name)

          const segment = (
            <ToggleGroupItem
              value={name}
              // Disabled rather than absent, and not rendered as a link:
              // a filter row whose items sometimes navigate elsewhere is
              // two controls wearing one coat.
              disabled={!usable}
              aria-label={usable ? label : `${label} — not connected`}
              className="flex-1 px-2 text-xs"
            >
              {SOURCE_MARKS[name] ?? label}
            </ToggleGroupItem>
          )

          return (
            <Tooltip key={name}>
              {/*
               * `span` around the trigger, because a disabled button fires
               * no pointer events and Radix would never hear the hover —
               * so the one control that needs an explanation would be the
               * one control with no tooltip.
               */}
              <TooltipTrigger asChild>
                {usable ? segment : <span className="flex flex-1">{segment}</span>}
              </TooltipTrigger>
              <TooltipContent>
                {usable ? label : `${label} — connect it in Settings`}
              </TooltipContent>
            </Tooltip>
          )
        })}
      </ToggleGroup>
    </div>
  )
}
