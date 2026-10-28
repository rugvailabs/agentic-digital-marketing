'use client'

import type { Brand, Platform, Region, SourceName, TrendsResponse } from '@trendforge/types'
import { useEffect, useRef, useState } from 'react'

import { Desk } from '@/components/Desk'
import { Ladder } from '@/components/Ladder'
import { BatchGenerate } from '@/components/BatchGenerate'
import { PlatformFilter } from '@/components/PlatformFilter'
import { RegionPicker } from '@/components/RegionPicker'
import { EmptyState } from '@/components/Empty'
import { Code, SectionLabel, cx } from '@/components/house'
import { formatIstTime } from '@/lib/format'

/**
 * Ladder (left, 420px) + Desk (right).
 *
 * Below --breakpoint-desk (800px) the ladder takes the full width and the Desk
 * arrives as a panel over it, opened by picking a topic: at that width a
 * side-by-side split leaves neither column readable.
 *
 * Only the selected rank is client state; the region lives in the URL so a
 * board is linkable and the server does the fetching.
 */
export function Board({
  regions,
  board,
  brands,
  platforms,
  activePlatform,
  openTrendId,
}: {
  regions: Region[]
  board: TrendsResponse
  brands: Brand[]
  platforms: Platform[]
  activePlatform?: SourceName
  /** A topic to open on, from a library or calendar row. */
  openTrendId?: number
}) {
  // Resolved once, at mount. The ladder is keyed by rank because that is
  // what a row shows and what the keyboard walks; a link names a topic by
  // id, because a rank is only true until the next merge.
  const [selectedRank, setSelectedRank] = useState(
    () => board.trends.find((t) => t.id === openTrendId)?.rank ?? board.trends[0]?.rank ?? 0,
  )
  const [panelOpen, setPanelOpen] = useState(false)
  /*
   * Which tab the Desk should open on when the selection changes.
   *
   * Lifted here because the request comes from the ladder: a row's
   * "Generate" has to both select the topic and land on the tab that
   * generates. Bumped with a counter rather than passed as a plain value,
   * so pressing Generate on the row that is already selected still moves
   * the Desk — a bare `openTab="post"` is unchanged in that case and the
   * Desk would stay on Evidence.
   */
  const [openOn, setOpenOn] = useState<{ tab: 'post'; nonce: number } | null>(null)
  const selected = board.trends.find((t) => t.rank === selectedRank) ?? board.trends[0] ?? null
  const closeRef = useRef<HTMLButtonElement>(null)

  // Escape closes the panel. On the wide layout there is no panel to close, so
  // the listener is only attached while one is open.
  useEffect(() => {
    if (!panelOpen) return
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPanelOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [panelOpen])

  function selectTopic(rank: number) {
    setSelectedRank(rank)
    // Only the narrow layout has a panel to open; on the wide one the
    // classes this flips on are each neutralised by a `desk:` counterpart.
    setPanelOpen(true)
  }

  function generateFor(rank: number) {
    selectTopic(rank)
    setOpenOn((previous) => ({ tab: 'post', nonce: (previous?.nonce ?? 0) + 1 }))
  }

  return (
    <div className="desk:flex-row flex min-h-[calc(100vh-var(--spacing-topbar))] flex-col">
      {/* Fixed 440px, and `shrink-0` so a long headline in the Desk cannot
          squeeze the column the headlines are in. */}
      <div className="desk:w-wire desk:border-r flex w-full shrink-0 flex-col border-border">
        <RegionPicker regions={regions} selected={board.region.code} />
        <PlatformFilter
          platforms={platforms}
          available={board.region.platforms}
          region={board.region.code}
          selected={activePlatform}
        />

        <BatchGenerate
          brands={brands}
          region={board.region.code}
          disabled={board.trends.length === 0}
        />

        <div className="flex items-baseline justify-between px-4 py-3">
          <SectionLabel>
            {board.count > 0 ? `${board.trends.length} of ${board.count} topics` : 'No topics yet'}
          </SectionLabel>
          {board.updated_at ? (
            <span className="num text-xs text-slate">
              updated {formatIstTime(board.updated_at)} IST
            </span>
          ) : null}
        </div>

        {board.trends.length === 0 ? (
          <div className="px-4 pb-6">
            <EmptyState
              art="ladder"
              title={`No topics for ${board.region.name} yet.`}
              hint={
                <>
                  Run <Code>.\tf.ps1 ingest</Code> to pull the first snapshot, or wait for the next
                  30-minute cycle.
                </>
              }
            />
          </div>
        ) : (
          <Ladder
            trends={board.trends}
            selectedRank={selectedRank}
            onSelect={selectTopic}
            onGenerate={generateFor}
          />
        )}
      </div>

      {/* Wide: a column. Narrow: a panel over the ladder, hidden until opened. */}
      <div
        className={cx(
          // A container, so the Desk's own grid can ask how wide *it* is
          // rather than how wide the window is. The two differ by the
          // sidebar, which collapses: at 1440 with the sidebar out there
          // are 760px here, and 480 + 420 does not fit in 760 — the rail
          // ran off the right of the screen. A viewport breakpoint cannot
          // see that, and railing the sidebar gives back 184px that the
          // rail could have used.
          '@container desk:static desk:block desk:w-auto desk:border-l-0 desk:bg-transparent min-w-0 flex-1',
          panelOpen
            ? // Starts below the 56px top bar, not at inset-y-0: the bar is
              // sticky at a higher z-index and would sit on top of the panel's
              // own Close row, leaving no way back to the ladder.
              //
              // Every one of these needs a `desk:` counterpart, including the
              // ones that look harmless. `max-w-[32rem]` had none, and since
              // clicking a row sets `panelOpen` on every layout, the Desk was
              // capped at 512px the moment you selected a topic at 1440 —
              // which is where the four hundred pixels of empty page beside
              // it came from. The comment below used to say these classes
              // never apply on the wide layout. Five of the six don't.
              'panel-in desk:max-w-none desk:animate-none desk:overflow-visible fixed top-topbar right-0 bottom-0 z-20 w-full max-w-[32rem] overflow-y-auto border-l border-border bg-page'
            : 'hidden',
        )}
        role={panelOpen ? 'dialog' : undefined}
        aria-label={panelOpen ? `${selected?.topic ?? 'Topic'} details` : undefined}
        aria-modal={panelOpen ? true : undefined}
      >
        <div className="desk:hidden sticky top-0 z-10 flex items-center border-b border-border bg-page px-4 py-2">
          <button
            ref={closeRef}
            type="button"
            onClick={() => setPanelOpen(false)}
            className="text-sm text-slate hover:text-ink"
          >
            Back to ladder
          </button>
        </div>
        <Desk
          region={board.region}
          trend={selected}
          brands={brands}
          platforms={platforms}
          openOn={openOn}
        />
      </div>
    </div>
  )
}
