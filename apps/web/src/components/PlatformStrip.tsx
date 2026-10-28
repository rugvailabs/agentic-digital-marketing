'use client'

import type { Platform } from '@trendforge/types'
import { SOURCE_LABELS, type SourceName } from '@trendforge/types'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useMemo, useRef } from 'react'

import { cx } from '@/components/ui'

/**
 * Platform filter above the ladder: All, then one per platform.
 *
 * Deliberately not pills. The selected state is an ink underline and a weight
 * change, the same idiom as the region strip directly above it, so the two
 * rows read as one navigation language rather than two widgets. It also keeps
 * the palette honest: chilli belongs to rising velocity and the focus ring,
 * turmeric to the curator's "watch" flag, and a filled chip would have to
 * borrow one of them.
 *
 * A platform with no credentials is still shown, as a link to the settings
 * page. Hiding it would read as a platform that does not exist, when what is
 * true is that nobody has pasted a key yet.
 *
 * Order is discovery sources first, then the places you post — the order of
 * the pipeline, not of the alphabet.
 */
export function PlatformStrip({
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
  const listRef = useRef<HTMLDivElement>(null)

  // Built from props rather than `useSearchParams()`. That hook opts the
  // whole route out of static rendering, and the page already has both
  // values from its own server-side searchParams — so reading them again on
  // the client bought nothing and cost the render path. It also left
  // Playwright's `networkidle` never settling, which is how it was noticed.
  const select = useCallback(
    (platform: SourceName | undefined) => {
      const next = new URLSearchParams({ region })
      if (platform) next.set('platform', platform)
      router.push(`/?${next.toString()}`, { scroll: false })
    },
    [region, router],
  )

  // Configured-and-covering first, then the rest. Within each group the
  // pipeline order from the types package is preserved.
  const ordered = useMemo(() => {
    const covers = new Set<string>(available)
    return [...platforms].sort((a, b) => Number(covers.has(b.name)) - Number(covers.has(a.name)))
  }, [platforms, available])

  const unconfigured = platforms.filter((p) => !p.configured).length
  const tabs: Array<SourceName | undefined> = [undefined, ...ordered.map((p) => p.name)]
  const index = Math.max(0, tabs.indexOf(selected))

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
          ? tabs.length - 1
          : Math.min(tabs.length - 1, Math.max(0, index + move))

    listRef.current?.querySelectorAll<HTMLElement>('[data-tab]')[next]?.focus()
    const target = tabs[next]
    // Only move the filter for a platform that can match something. An
    // unconfigured one is a link to settings, and arrowing onto it must not
    // empty the board.
    if (target === undefined || available.includes(target)) select(target)
  }

  return (
    // Scrolling tabs in a flexible child with the trailing link pinned
    // outside it, the same shape as the region strip's "Jump to…". With the
    // link inside the scroller it was the thing that scrolled off, so the
    // row ended on a clipped "Conne…".
    <div className="flex items-center border-b border-border pr-3">
      <div
        ref={listRef}
        role="tablist"
        aria-label="Platform"
        aria-orientation="horizontal"
        onKeyDown={onKeyDown}
        className="flex min-w-0 flex-1 items-center gap-3 overflow-x-auto py-2 pr-1 pl-4 [scrollbar-width:thin]"
      >
        <Tab
          label="All"
          isSelected={selected === undefined}
          tabIndex={index === 0 ? 0 : -1}
          onSelect={() => select(undefined)}
        />

        {ordered.map((platform, i) => {
          const name = platform.name as SourceName
          const label = SOURCE_LABELS[name] ?? name
          const covers = available.includes(name)

          if (!platform.configured) {
            return (
              <Link
                key={name}
                href="/settings"
                data-tab
                role="tab"
                aria-selected={false}
                tabIndex={index === i + 1 ? 0 : -1}
                // The chip is the affordance; the word "connect" is not
                // repeated on each one. Seven labels plus "connect" twice
                // overflowed the 420px wire column and clipped the last chip
                // to "Instagram c…", so the state is carried by the dotted
                // underline and said once, at the end of the row.
                title={`${label} is not connected — set ${platform.env_vars.join(' and ')}`}
                className="shrink-0 border-b-2 border-dotted border-rule py-1 text-sm whitespace-nowrap text-slate hover:border-slate hover:text-ink"
              >
                {label}
              </Link>
            )
          }

          return (
            <Tab
              key={name}
              label={label}
              isSelected={selected === name}
              // Configured but not covering this region: YouTube's chart is
              // national, Reddit needs a mapped subreddit. Shown greyed rather
              // than hidden, because the platform exists and the region is the
              // reason it is empty.
              isDisabled={!covers}
              title={covers ? undefined : `${label} has no data for this region`}
              tabIndex={index === i + 1 ? 0 : -1}
              onSelect={() => select(name)}
            />
          )
        })}
      </div>

      {platforms.length === 0 ? (
        // Never a real state: Google Trends and Google News need no
        // credentials, so the list is only ever empty when the fetch failed.
        // Rendering a bare "All" would read as a deployment with no
        // platforms at all, which is a very different thing from one whose
        // API answered badly.
        <span className="shrink-0 border-l border-border py-1 pl-3 text-xs whitespace-nowrap text-slate">
          Platform list unavailable
        </span>
      ) : null}

      {unconfigured > 0 ? (
        <Link
          href="/settings"
          // Not a tab: it filters nothing. It is the one place the word
          // "connect" is said, and it explains the dotted chips beside it.
          title={`${unconfigured} platforms need credentials`}
          className="shrink-0 border-l border-border py-1 pl-3 text-xs whitespace-nowrap text-slate hover:text-ink"
        >
          Connect {unconfigured}
        </Link>
      ) : null}
    </div>
  )
}

function Tab({
  label,
  isSelected,
  isDisabled = false,
  title,
  tabIndex,
  onSelect,
}: {
  label: string
  isSelected: boolean
  isDisabled?: boolean
  title?: string
  tabIndex: number
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      data-tab
      role="tab"
      aria-selected={isSelected}
      aria-disabled={isDisabled || undefined}
      disabled={isDisabled}
      tabIndex={tabIndex}
      title={title}
      onClick={onSelect}
      className={cx(
        'shrink-0 border-b-2 py-1 text-sm whitespace-nowrap transition-colors',
        isSelected ? 'border-ink font-medium text-ink' : 'border-transparent',
        !isSelected && !isDisabled ? 'text-ink hover:border-border' : '',
        isDisabled ? 'cursor-not-allowed text-rule' : '',
      )}
    >
      {label}
    </button>
  )
}
