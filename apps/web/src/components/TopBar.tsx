import type { Health } from '@trendforge/types'

import { IstClock } from '@/components/IstClock'

/**
 * 56px fixed bar: app name, what you are looking at, IST clock, pipeline dot.
 * Nothing else — the avoid-list rules out a row of stat tiles here, and the
 * middle-dot meta string is gone: the region is simply weighted up.
 */
export function TopBar({ health, regionName }: { health: Health | null; regionName?: string }) {
  const pipeline = pipelineState(health)

  return (
    <header className="sticky top-0 z-30 flex h-topbar items-center gap-6 border-b border-rule bg-surface px-5">
      <span className="font-display text-lg font-extrabold tracking-tight text-ink">
        TrendForge
      </span>
      {/* The region is named in the strip too, so this is the first thing to
          go when the bar runs out of room. */}
      <span className="hidden truncate text-xs text-slate sm:inline">
        Trend desk{' '}
        {regionName ? <span className="text-sm font-medium text-ink">{regionName}</span> : null}
      </span>

      <div className="ml-auto flex shrink-0 items-center gap-5">
        <IstClock />
        {/* CLAUDE.md requires the clock and the dot; the wording next to the
            dot is ours, so on a phone the dot carries the state alone and the
            label survives as its accessible name. */}
        <span className="flex items-center gap-2 text-xs text-slate" title={pipeline.label}>
          <span
            role="img"
            aria-label={pipeline.label}
            className="size-2 rounded-full"
            style={{ backgroundColor: pipeline.color }}
          />
          <span className="hidden sm:inline">{pipeline.label}</span>
        </span>
      </div>
    </header>
  )
}

function pipelineState(health: Health | null): { label: string; color: string } {
  if (!health) {
    return { label: 'API unreachable', color: 'var(--color-slate)' }
  }
  if (health.status !== 'ok' || !health.database) {
    return { label: 'Degraded', color: 'var(--color-turmeric)' }
  }
  const sources = health.sources_configured.length
  return {
    label: `Ingest ok, ${sources} ${sources === 1 ? 'source' : 'sources'}`,
    color: 'var(--color-neem)',
  }
}
