'use client'

import type { Region } from '@trendforge/types'
import { Check, ChevronDown } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { cx } from '@/components/house'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

/** Where the recent regions are kept. Local, like the theme and the rail. */
const RECENT_KEY = 'trendforge.recent-regions'
const PINNED = 6

/**
 * Order: India, then states by today's total topic volume, then union
 * territories, then cities.
 *
 * Volume rather than alphabetical because this is a work queue — the states
 * with the most happening are the ones a marketer opens first, and
 * alphabetical buries Tamil Nadu and Maharashtra behind Andaman and Nicobar.
 * Within each tier a zero-volume region falls back to its name, so the tail
 * stays predictable instead of shuffling on every ingest.
 */
function order(regions: Region[]): Region[] {
  const tier: Record<string, number> = { country: 0, state: 1, union_territory: 2, city: 3 }
  return [...regions].sort((a, b) => {
    const byTier = (tier[a.kind] ?? 9) - (tier[b.kind] ?? 9)
    if (byTier !== 0) return byTier
    // Coalesce: a response predating total_volume would compare undefined to
    // undefined and silently fall back to alphabetical.
    const volume = (b.total_volume ?? 0) - (a.total_volume ?? 0)
    if (volume !== 0) return volume
    return a.name.localeCompare(b.name)
  })
}

function readRecent(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
    return Array.isArray(raw) ? raw.filter((c): c is string => typeof c === 'string') : []
  } catch {
    return []
  }
}

/**
 * One combobox and six chips, in place of a horizontal strip of 53 regions.
 *
 * The strip could not be made to fit. At 440px it showed four and a half
 * names — "India Maharashtra Uttar Pradesh B|" — and the overflow was a
 * scroll nobody could see the end of, with a "Jump to…" select bolted on
 * beside it that did the same job twice. Fifty-three regions is a search
 * problem, not a tab-bar problem.
 *
 * So: the current region as a button that opens a searchable list, and
 * beside it the six you actually use. Those are the recent ones rather
 * than the biggest ones, because a marketer works a handful of states and
 * the sixth-largest by volume is not one of them.
 */
export function RegionPicker({ regions, selected }: { regions: Region[]; selected: string }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [recent, setRecent] = useState<string[]>([])
  const ordered = useMemo(() => order(regions), [regions])
  const byCode = useMemo(() => new Map(ordered.map((r) => [r.code, r])), [ordered])
  const current = byCode.get(selected)

  // Read in an effect, not in the initial state: this renders on the server
  // first, and localStorage read during render is a hydration mismatch.
  useEffect(() => setRecent(readRecent()), [])

  // Record the visit, most recent first. Written on arrival rather than on
  // click so a region reached from the dashboard map or a library link
  // counts too — those are visits, and the chips are about where you work.
  useEffect(() => {
    setRecent((previous) => {
      const next = [selected, ...previous.filter((code) => code !== selected)].slice(0, 12)
      try {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next))
      } catch {
        // A private window with storage denied still gets the combobox.
      }
      return next
    })
  }, [selected])

  const select = useCallback(
    (code: string) => {
      setOpen(false)
      router.push(`/board?region=${encodeURIComponent(code)}`, { scroll: false })
    },
    [router],
  )

  /*
   * The chips: what you have opened, topped up from the top of the ordered
   * list so the row is never half empty on a first visit. Always includes
   * the current region, so the selected chip is visible rather than being
   * the one that fell off the end.
   */
  const pinned = useMemo(() => {
    const codes: string[] = []
    for (const code of [selected, ...recent, ...ordered.map((r) => r.code)]) {
      if (!codes.includes(code) && byCode.has(code)) codes.push(code)
      if (codes.length === PINNED) break
    }
    return codes.map((code) => byCode.get(code)!)
  }, [selected, recent, ordered, byCode])

  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-3 py-2.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            role="combobox"
            aria-expanded={open}
            aria-label="Change region"
            className="font-medium"
          >
            {current?.name ?? 'Pick a region'}
            <ChevronDown aria-hidden="true" className="size-3.5 text-slate" strokeWidth={2} />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72 p-0">
          <Command
            filter={(value, search) =>
              // Substring, not shadcn's fuzzy default. "Tamil" fuzzily
              // matches "Jammu and Kashmir" well enough to rank it above
              // Tamil Nadu, which is not what anyone typing it wants.
              value.toLowerCase().includes(search.toLowerCase()) ? 1 : 0
            }
          >
            <CommandInput placeholder="Search regions" />
            <CommandList>
              <CommandEmpty>No region by that name.</CommandEmpty>
              <CommandGroup>
                {ordered.map((region) => (
                  <CommandItem
                    key={region.code}
                    value={region.name}
                    onSelect={() => select(region.code)}
                  >
                    <Check
                      aria-hidden="true"
                      className={cx(
                        'size-3.5',
                        region.code === selected ? 'opacity-100' : 'opacity-0',
                      )}
                      strokeWidth={2.5}
                    />
                    <span className="flex-1 truncate">{region.name}</span>
                    <span className="font-mono text-xs text-faint">{region.code}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {/* The pinned six. Buttons, not links: the region is a query param on
          this same route, and a full navigation would discard the ladder. */}
      {pinned.map((region) => {
        const active = region.code === selected
        return (
          <button
            key={region.code}
            type="button"
            onClick={() => select(region.code)}
            aria-current={active ? 'true' : undefined}
            className={cx(
              'rounded-sm border px-2 py-1 text-xs whitespace-nowrap transition-colors duration-150 ease-[var(--ease-out-quick)]',
              active
                ? 'border-border-hover bg-accent text-ink'
                : 'border-border text-slate hover:border-border-hover hover:text-ink',
            )}
          >
            {region.name}
          </button>
        )
      })}
    </div>
  )
}
