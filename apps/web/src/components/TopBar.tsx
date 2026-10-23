import type { Health } from '@trendforge/types'

import { IstClock } from '@/components/IstClock'
import { cx } from '@/components/primitives'

/**
 * 56px fixed bar: app name, IST clock, pipeline dot. Nothing else — the
 * avoid-list rules out a row of stat tiles here.
 */
export function TopBar({ health }: { health: Health | null }) {
  const state = pipelineState(health)

  return (
    <header className="sticky top-0 z-10 flex h-topbar items-center gap-6 border-b border-rule bg-surface px-5">
      <span className="font-display text-lg font-extrabold tracking-tight text-ink">
        TrendForge
      </span>
      <span className="text-xs text-slate">Trend desk · India</span>

      <div className="ml-auto flex items-center gap-5">
        <IstClock />
        <span className="flex items-center gap-2 text-xs text-slate">
          <span
            aria-hidden
            className={cx('size-2 rounded-full', state.dot)}
            style={state.style}
          />
          {state.label}
        </span>
      </div>
    </header>
  )
}

function pipelineState(health: Health | null): {
  label: string
  dot: string
  style?: React.CSSProperties
} {
  if (!health) {
    return { label: 'API unreachable', dot: '', style: { backgroundColor: 'var(--color-slate)' } }
  }
  if (health.status !== 'ok' || !health.database) {
    return { label: 'Degraded', dot: '', style: { backgroundColor: 'var(--color-turmeric)' } }
  }
  const sources = health.sources_configured.length
  return {
    label: `Ingest ok · ${sources} ${sources === 1 ? 'source' : 'sources'}`,
    dot: '',
    style: { backgroundColor: 'var(--color-neem)' },
  }
}
