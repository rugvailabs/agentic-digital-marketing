import type { ReactNode } from 'react'

/**
 * Our own primitives — no component kit, per CLAUDE.md. Everything here is
 * flat: no shadows, no radii, no gradients, no fills. Grouping comes from
 * rules and spacing, and colour is spent only on rising velocity.
 */

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/**
 * A small capsule naming a source or a category. Slate text on a 1px rule
 * border, never filled and never accented — a chip is a label, not a signal.
 */
export function Chip({
  children,
  className,
  title,
}: {
  children: ReactNode
  /** For the ladder's category chip, which has to truncate inside its border. */
  className?: string
  /** Full text when the label is shortened or truncated. */
  title?: string
}) {
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center border border-rule px-1.5 py-px text-xs leading-5 whitespace-nowrap text-slate',
        className,
      )}
    >
      {children}
    </span>
  )
}

/**
 * One cell of the Desk's meta row: a label above its value.
 *
 * On the wide layout the cells sit on one line divided by hairline rules, so
 * the group reads as a single sentence of facts rather than four boxes. The
 * rules are dropped below the Desk breakpoint, where the row has to wrap and a
 * leading rule on the wrapped cell is an orphan.
 */
export function MetaCell({
  label,
  numeric = false,
  children,
}: {
  label: string
  /** Tabular figures. Only for actual numbers — it widens letterforms too. */
  numeric?: boolean
  children: ReactNode
}) {
  return (
    <div className="desk:pr-5 desk:pl-5 desk:first:pl-0 desk:last:pr-0 desk:not-first:border-l flex flex-col gap-0.5 border-rule">
      <span className="text-xs text-slate">{label}</span>
      <span className={cx('text-sm text-ink', numeric && 'num')}>{children}</span>
    </div>
  )
}

/** Section heading: sentence case, slate, 12px. Not an all-caps eyebrow. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return <h2 className="text-xs font-medium text-slate">{children}</h2>
}

/** Empty state. Always says what to do next. */
export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="border-t border-rule pt-4">
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
