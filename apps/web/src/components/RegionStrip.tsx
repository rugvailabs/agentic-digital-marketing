'use client'

import type { Region } from '@trendforge/types'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef } from 'react'

import { cx } from '@/components/primitives'

/**
 * Order: India, then states by today's total topic volume, then union
 * territories, then cities.
 *
 * Volume rather than alphabetical because the strip is a work queue — the
 * states with the most happening are the ones a marketer opens first, and
 * alphabetical buries Tamil Nadu and Maharashtra behind Andaman and Nicobar.
 * Within each tier a zero-volume region falls back to its name, so the tail
 * stays predictable instead of shuffling on every ingest.
 */
function order(regions: Region[]): Region[] {
  const tier: Record<string, number> = { country: 0, state: 1, union_territory: 2, city: 3 }
  return [...regions].sort((a, b) => {
    const byTier = (tier[a.kind] ?? 9) - (tier[b.kind] ?? 9)
    if (byTier !== 0) return byTier
    // Coalesce: a response that predates total_volume would otherwise compare
    // undefined to undefined and silently fall back to alphabetical.
    const volume = (b.total_volume ?? 0) - (a.total_volume ?? 0)
    if (volume !== 0) return volume
    return a.name.localeCompare(b.name)
  })
}

export function RegionStrip({
  regions,
  selected,
}: {
  regions: Region[]
  selected: string
}) {
  const router = useRouter()
  const listRef = useRef<HTMLDivElement>(null)
  const ordered = useMemo(() => order(regions), [regions])
  const index = Math.max(
    0,
    ordered.findIndex((r) => r.code === selected),
  )

  const select = useCallback(
    (code: string) => {
      router.push(`/?region=${encodeURIComponent(code)}`, { scroll: false })
    },
    [router],
  )

  // Keep the active tab in view when the region changes from anywhere,
  // including from the jump menu below.
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
          ? ordered.length - 1
          : Math.min(ordered.length - 1, Math.max(0, index + move))

    const code = ordered[next]?.code
    if (!code) return
    listRef.current?.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus()
    select(code)
  }

  return (
    <div className="flex items-center gap-2 border-b border-rule bg-surface pr-3">
      <div
        ref={listRef}
        role="tablist"
        aria-label="Region"
        aria-orientation="horizontal"
        onKeyDown={onKeyDown}
        className="flex min-w-0 flex-1 gap-2 overflow-x-auto py-2 pr-1 pl-4 [scrollbar-width:thin]"
      >
        {ordered.map((region, i) => {
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
                'shrink-0 border-b-2 px-1 py-1 text-sm whitespace-nowrap transition-colors',
                isSelected
                  ? 'border-ink font-medium text-ink'
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

      <JumpTo regions={ordered} onSelect={select} />
    </div>
  )
}

/**
 * The strip scrolls, so the 40th region is reachable only by arrowing through
 * 39 others. A native select is the one control that gives keyboard and screen
 * reader users direct access without inventing a combobox.
 *
 * It holds no value of its own — it always reads "Jump to…" — because the
 * strip already shows the current region, and a select bound to the selection
 * sizes itself to its longest option ("Andaman and Nicobar Islands") and eats
 * the 420px column.
 */
function JumpTo({ regions, onSelect }: { regions: Region[]; onSelect: (code: string) => void }) {
  const groups: Array<[string, Region[]]> = [
    ['India', regions.filter((r) => r.kind === 'country')],
    ['States', regions.filter((r) => r.kind === 'state')],
    ['Union territories', regions.filter((r) => r.kind === 'union_territory')],
    ['Cities', regions.filter((r) => r.kind === 'city')],
  ]

  return (
    <select
      aria-label="Jump to region"
      value=""
      onChange={(event) => {
        if (event.target.value) onSelect(event.target.value)
      }}
      className="w-24 shrink-0 border border-rule bg-surface px-1.5 py-1 text-xs text-slate"
    >
      <option value="">Jump to…</option>
      {groups.map(([label, members]) =>
        members.length === 0 ? null : (
          <optgroup key={label} label={label}>
            {members.map((r) => (
              <option key={r.code} value={r.code}>
                {r.name}
              </option>
            ))}
          </optgroup>
        ),
      )}
    </select>
  )
}
