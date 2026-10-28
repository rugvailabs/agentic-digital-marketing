'use client'

import type { Health } from '@trendforge/types'
import { useEffect, useState } from 'react'

import { GlobalSearch } from '@/components/shell/GlobalSearch'
import { IstClock } from '@/components/IstClock'
import { cx } from '@/components/house'

/**
 * 56px of system state, and the search.
 *
 * What is here has not changed — the IST clock and the pipeline dot are
 * both required by CLAUDE.md — but what is *not* here has: the product
 * name moved to the sidebar, because the top bar is for the state of the
 * system and the name of the product is not state.
 *
 * Health is polled from the client rather than passed down from a server
 * render. It is a live value: a server-rendered one is frozen at the
 * moment the page was requested, so a dot that said "ok" could keep saying
 * it for an hour after the worker died.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

/** Often enough to notice a stall, rarely enough to be free. */
const POLL_MS = 30_000

export function TopBar() {
  const health = useHealth()
  const pipeline = pipelineState(health)

  return (
    <header className="sticky top-0 z-30 flex h-topbar items-center gap-4 border-b border-border bg-panel px-4">
      <div className="min-w-0 flex-1">
        <GlobalSearch />
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <IstClock />
        {/* CLAUDE.md requires the clock and the dot; the wording next to the
            dot is ours, so on a phone the dot carries the state alone and
            the label survives as its accessible name. */}
        <span className="flex items-center gap-2 text-xs text-slate" title={pipeline.label}>
          <span
            role="img"
            aria-label={pipeline.label}
            className={cx('size-2 rounded-full', pipeline.pulse && 'animate-pulse')}
            style={{ backgroundColor: pipeline.color }}
          />
          <span className="hidden sm:inline">{pipeline.label}</span>
        </span>
      </div>
    </header>
  )
}

function useHealth(): Health | null | undefined {
  // undefined is "not asked yet" and null is "asked and could not reach
  // it". The dot must not claim the API is down during the first 200ms of
  // every page load, which is what one state for both would do.
  const [health, setHealth] = useState<Health | null | undefined>(undefined)

  useEffect(() => {
    let alive = true

    async function check() {
      try {
        const response = await fetch(`${API}/health`, { cache: 'no-store' })
        if (!response.ok) throw new Error(String(response.status))
        const body = (await response.json()) as Health
        if (alive) setHealth(body)
      } catch {
        if (alive) setHealth(null)
      }
    }

    void check()
    const timer = setInterval(() => void check(), POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  return health
}

/**
 * Colours per the palette. Neem and turmeric carry velocity and
 * sensitivity, so neither belongs on a system-health dot. A working
 * pipeline is not news — slate. A broken one is the most urgent thing on
 * the screen, which is what chilli is for.
 */
function pipelineState(health: Health | null | undefined): {
  label: string
  color: string
  pulse: boolean
} {
  if (health === undefined) {
    return { label: 'Checking', color: 'var(--color-muted)', pulse: true }
  }
  if (health === null) {
    return { label: 'API unreachable', color: 'var(--color-chilli)', pulse: false }
  }
  if (health.status !== 'ok' || !health.database) {
    return { label: 'Degraded', color: 'var(--color-chilli)', pulse: false }
  }
  const sources = health.sources_configured.length
  return {
    label: `Ingest ok, ${sources} ${sources === 1 ? 'source' : 'sources'}`,
    color: 'var(--color-slate)',
    pulse: false,
  }
}
