'use client'

import type { Region, TrendsResponse } from '@trendforge/types'
import { useEffect, useRef, useState } from 'react'

import { Desk } from '@/components/Desk'
import { Ladder } from '@/components/Ladder'
import { RegionStrip } from '@/components/RegionStrip'
import { Code, Empty, SectionLabel, cx } from '@/components/primitives'
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
}: {
  regions: Region[]
  board: TrendsResponse
}) {
  const [selectedRank, setSelectedRank] = useState(board.trends[0]?.rank ?? 0)
  const [panelOpen, setPanelOpen] = useState(false)
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
    // Harmless on the wide layout, where the panel classes never apply.
    setPanelOpen(true)
  }

  return (
    <div className="desk:flex-row flex min-h-[calc(100vh-var(--spacing-topbar))] flex-col">
      <div className="desk:w-wire desk:border-r flex w-full shrink-0 flex-col border-rule">
        <RegionStrip regions={regions} selected={board.region.code} />

        <div className="flex items-baseline justify-between px-4 py-3">
          <SectionLabel>
            {board.count > 0
              ? `${board.trends.length} of ${board.count} topics`
              : 'No topics yet'}
          </SectionLabel>
          {board.updated_at ? (
            <span className="num text-xs text-slate">
              updated {formatIstTime(board.updated_at)} IST
            </span>
          ) : null}
        </div>

        {board.trends.length === 0 ? (
          <div className="px-4 pb-6">
            <Empty
              title={`No topics for ${board.region.name} yet.`}
              hint={
                <>
                  Run <Code>.\tf.ps1 ingest</Code> to pull the first snapshot, or wait for the
                  next 30-minute cycle.
                </>
              }
            />
          </div>
        ) : (
          <Ladder trends={board.trends} selectedRank={selectedRank} onSelect={selectTopic} />
        )}
      </div>

      {/* Wide: a column. Narrow: a panel over the ladder, hidden until opened. */}
      <div
        className={cx(
          'desk:static desk:block desk:w-auto desk:border-l-0 desk:bg-transparent min-w-0 flex-1',
          panelOpen
            ? // Starts below the 56px top bar, not at inset-y-0: the bar is
              // sticky at a higher z-index and would sit on top of the panel's
              // own Close row, leaving no way back to the ladder.
              'panel-in fixed top-topbar right-0 bottom-0 z-20 w-full max-w-[32rem] overflow-y-auto border-l border-rule bg-paper'
            : 'hidden',
        )}
        role={panelOpen ? 'dialog' : undefined}
        aria-label={panelOpen ? `${selected?.topic ?? 'Topic'} details` : undefined}
        aria-modal={panelOpen ? true : undefined}
      >
        <div className="desk:hidden sticky top-0 z-10 flex items-center border-b border-rule bg-paper px-4 py-2">
          <button
            ref={closeRef}
            type="button"
            onClick={() => setPanelOpen(false)}
            className="text-sm text-slate hover:text-ink"
          >
            Back to ladder
          </button>
        </div>
        <Desk region={board.region} trend={selected} />
      </div>
    </div>
  )
}
