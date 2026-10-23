'use client'

import type { Region } from '@trendforge/types'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef } from 'react'

import { cx } from '@/components/primitives'

/**
 * Horizontally scrollable region selector.
 *
 * A tablist rather than a <select>: there are 53 regions and switching between
 * neighbours is the main motion of the board, so arrow keys have to work. The
 * selected region is marked with a 2px chilli underline — a pill would turn
 * this into the row of identical rounded chips the avoid-list rejects.
 */
export function RegionStrip({
  regions,
  selected,
}: {
  regions: Region[]
  selected: string
}) {
  const router = useRouter()
  const listRef = useRef<HTMLDivElement>(null)
  const index = Math.max(
    0,
    regions.findIndex((r) => r.code === selected),
  )

  const select = useCallback(
    (code: string) => {
      router.push(`/?region=${encodeURIComponent(code)}`, { scroll: false })
    },
    [router],
  )

  // Keep the active tab in view when the region changes from anywhere.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[aria-selected="true"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [selected])

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number | 'first' | 'last'> = {
      ArrowRight: 1,
      ArrowLeft: -1,
      Home: 'first',
      End: 'last',
    }
    const move = moves[event.key]
    if (move === undefined) return

    event.preventDefault()
    const next =
      move === 'first'
        ? 0
        : move === 'last'
          ? regions.length - 1
          : Math.min(regions.length - 1, Math.max(0, index + move))

    const code = regions[next]?.code
    if (!code) return
    const target = listRef.current?.querySelectorAll<HTMLElement>('[role="tab"]')[next]
    target?.focus()
    select(code)
  }

  return (
    <div className="border-b border-rule bg-surface">
      <div
        ref={listRef}
        role="tablist"
        aria-label="Region"
        aria-orientation="horizontal"
        onKeyDown={onKeyDown}
        className="flex gap-1 overflow-x-auto px-4 py-2 [scrollbar-width:thin]"
      >
        {regions.map((region, i) => {
          const isSelected = region.code === selected
          return (
            <button
              key={region.code}
              type="button"
              role="tab"
              aria-selected={isSelected}
              // Roving tabindex: one stop for the whole strip, arrows move within.
              tabIndex={i === index ? 0 : -1}
              onClick={() => select(region.code)}
              title={
                region.trend_count
                  ? `${region.name} — ${region.trend_count} topics`
                  : `${region.name} — no topics yet`
              }
              className={cx(
                'shrink-0 border-b-2 px-2.5 py-1 text-sm whitespace-nowrap transition-colors',
                isSelected
                  ? 'border-chilli font-medium text-ink'
                  : 'border-transparent hover:bg-row-hover',
                // A region with no board reads quieter rather than disappearing:
                // the strip must always show all 36 states and UTs.
                !isSelected && region.trend_count === 0 ? 'text-slate' : '',
                !isSelected && region.trend_count > 0 ? 'text-ink' : '',
              )}
            >
              {region.name}
            </button>
          )
        })}
      </div>
    </div>
  )
}
