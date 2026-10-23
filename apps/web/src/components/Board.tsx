'use client'

import type { Region, TrendsResponse } from '@trendforge/types'
import { useState } from 'react'

import { Desk } from '@/components/Desk'
import { Ladder } from '@/components/Ladder'
import { RegionStrip } from '@/components/RegionStrip'
import { Code, Empty, SectionLabel } from '@/components/primitives'
import { formatIstTime } from '@/lib/format'

/**
 * Wire (left) + Desk (right). Only the selected rank is client state; the
 * region lives in the URL so a board is linkable and the server does the
 * fetching.
 */
export function Board({
  regions,
  board,
}: {
  regions: Region[]
  board: TrendsResponse
}) {
  const [selectedRank, setSelectedRank] = useState(board.trends[0]?.rank ?? 0)
  const selected = board.trends.find((t) => t.rank === selectedRank) ?? board.trends[0] ?? null

  return (
    <div className="flex min-h-[calc(100vh-var(--spacing-topbar))] flex-col lg:flex-row">
      <div className="flex w-full shrink-0 flex-col border-rule lg:w-wire lg:border-r">
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
          <Ladder
            trends={board.trends}
            selectedRank={selectedRank}
            onSelect={setSelectedRank}
          />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <Desk region={board.region} trend={selected} />
      </div>
    </div>
  )
}
