import type { ReactNode } from 'react'

/**
 * Our own primitives — no component kit, per CLAUDE.md. Everything here is
 * flat: no shadows, no radii beyond 2px, no gradients. Grouping comes from
 * rules and spacing.
 */

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/** A small capsule naming a source or state. Text only, never an icon. */
export function Chip({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'accent'
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center border px-1.5 py-px text-xs leading-5 whitespace-nowrap',
        tone === 'accent'
          ? 'border-chilli/40 text-chilli'
          : 'border-rule text-slate',
      )}
    >
      {children}
    </span>
  )
}

/**
 * A labelled value. Replaces the middle-dot meta string the avoid-list
 * rejects: the label is always visible, so nothing has to be inferred from
 * position.
 */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate">{label}</span>
      <span className="num text-sm text-ink">{children}</span>
    </div>
  )
}

/** Section heading: sentence case, slate, 12px. Not an all-caps eyebrow. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return <h2 className="text-xs font-medium text-slate">{children}</h2>
}

/**
 * The only boxed container in the app. Reserved for generated assets and the
 * studio placeholder, so a border means "asset" rather than "content".
 */
export function AssetFrame({ children }: { children: ReactNode }) {
  return (
    <div className="border border-rule bg-surface p-5">{children}</div>
  )
}

/** Empty state. Always says what to do next. */
export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="border border-dashed border-rule px-5 py-8">
      <p className="text-sm text-ink">{title}</p>
      {hint ? <p className="mt-1.5 text-sm text-slate">{hint}</p> : null}
    </div>
  )
}

/** Inline code, used in empty-state hints that name a command. */
export function Code({ children }: { children: ReactNode }) {
  return (
    <code className="border border-rule px-1 py-px font-mono text-xs text-ink">{children}</code>
  )
}
