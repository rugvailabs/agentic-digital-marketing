import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import type { SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'

/**
 * The control system.
 *
 * Still our own — no component kit, per CLAUDE.md. What is new is that
 * every state is written down once here instead of being re-decided in
 * every file: a button in the Desk and a button in the calendar were
 * different shades of the same intention, and four of them had no disabled
 * style at all.
 *
 * Four states, for everything:
 *
 *   rest       the thing as it sits
 *   hover      the line brightens — that is the house signal for "this is
 *              interactive", and it is the only one that works equally well
 *              in both themes
 *   active     it moves a pixel toward you, so a click feels like a click
 *   focus      the 2px chilli ring from globals.css, never overridden
 *   disabled   40% and not-allowed, never a different colour — a greyed
 *              control that is a different grey from the text around it
 *              reads as a bug
 *
 * Nothing here branches on theme. A control names a surface token and the
 * surface knows what it looks like in each.
 */

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/* ── Surfaces ──────────────────────────────────────────────────────────── */

type SurfaceTone = 'page' | 'panel' | 'card' | 'overlay'

const SURFACE: Record<SurfaceTone, string> = {
  page: 'bg-page',
  panel: 'bg-panel',
  card: 'bg-card',
  overlay: 'bg-overlay shadow-overlay',
}

/**
 * A region of the page: the sidebar, a dashboard section, the Desk.
 *
 * A panel is not interactive and does not lift. If you are reaching for a
 * panel that lifts you want a Card.
 */
export function Panel({
  tone = 'panel',
  className,
  children,
  ...rest
}: {
  tone?: SurfaceTone
  className?: string
  children: ReactNode
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx('rounded-lg border border-border', SURFACE[tone], className)} {...rest}>
      {children}
    </div>
  )
}

/**
 * A discrete object you can act on.
 *
 * `interactive` is what turns on the 4px lift. A card that only displays
 * something should not move when the pointer crosses it — motion is a
 * promise that clicking does something.
 */
export function Card({
  interactive = false,
  className,
  children,
  ...rest
}: {
  interactive?: boolean
  className?: string
  children: ReactNode
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        'rounded-md border border-border bg-card',
        interactive && 'lift cursor-pointer',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

/* ── Buttons ───────────────────────────────────────────────────────────── */

export type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'danger'
export type ControlSize = 'sm' | 'md'

/**
 * Primary is an ink fill, not a chilli one.
 *
 * Chilli has exactly three jobs in this product — rising velocity, the
 * focus ring, and destroying something — and a filled primary button on
 * every screen would drown all three. In dark mode an ink fill is a light
 * button on a dark ground, which is the strongest thing on the page
 * without spending the accent.
 */
const VARIANT: Record<ButtonVariant, string> = {
  primary: cx(
    'border border-ink bg-ink text-page',
    'hover:border-ink/90 hover:bg-ink/90',
    'active:bg-ink/80',
  ),
  secondary: cx(
    'border border-border bg-card text-ink',
    'hover:border-border-hover hover:bg-overlay',
    'active:bg-card',
  ),
  quiet: cx(
    'border border-transparent text-slate',
    'hover:border-border hover:bg-row-hover hover:text-ink',
    'active:bg-row-active',
  ),
  danger: cx(
    'border border-chilli bg-transparent text-chilli',
    'hover:bg-chilli hover:text-chilli-ink',
    'active:opacity-90',
  ),
}

const SIZE: Record<ControlSize, string> = {
  sm: 'h-7 gap-1.5 px-2.5 text-xs',
  md: 'h-9 gap-2 px-3.5 text-sm',
}

/** Every control that can be pressed is this height, so a row of them lines up. */
export const CONTROL_HEIGHT: Record<ControlSize, string> = { sm: 'h-7', md: 'h-9' }

const PRESSABLE = cx(
  'inline-flex items-center justify-center rounded-sm whitespace-nowrap',
  'transition-[background-color,border-color,color,transform] duration-150',
  'disabled:pointer-events-none disabled:opacity-40',
)

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  children,
  ...rest
}: {
  variant?: ButtonVariant
  size?: ControlSize
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cx(PRESSABLE, VARIANT[variant], SIZE[size], 'active:translate-y-px', className)}
      {...rest}
    >
      {children}
    </button>
  )
}

/**
 * A square button carrying only an icon.
 *
 * `label` is required, not optional — CLAUDE.md asks that every icon have a
 * label, and an optional one is a label that will not be there.
 */
export function IconButton({
  label,
  variant = 'quiet',
  size = 'md',
  className,
  children,
  ...rest
}: {
  label: string
  variant?: ButtonVariant
  size?: ControlSize
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'>) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        PRESSABLE,
        VARIANT[variant],
        size === 'sm' ? 'size-7' : 'size-9',
        'active:translate-y-px',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}

/**
 * A link that looks like a button.
 *
 * Separate from Button rather than a polymorphic `as` prop: the two have
 * different disabled semantics — a link cannot be disabled, it can only be
 * absent — and a shared component would quietly offer one that does nothing.
 */
export function ButtonLink({
  variant = 'secondary',
  size = 'md',
  className,
  children,
  ...rest
}: {
  variant?: ButtonVariant
  size?: ControlSize
} & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      className={cx(PRESSABLE, VARIANT[variant], SIZE[size], 'active:translate-y-px', className)}
      {...rest}
    >
      {children}
    </a>
  )
}

/* ── Fields ────────────────────────────────────────────────────────────── */

/**
 * Inputs sit one step *below* their surface, not on it.
 *
 * `bg-page` inside a card is darker in dark mode and lighter-grey in light
 * mode, and in both it reads as somewhere to type rather than as another
 * card. A field the same colour as the card it sits on needs its border to
 * do all the work, and a 1px border is not enough work.
 */
const FIELD = cx(
  'w-full rounded-sm border border-border bg-page text-ink',
  'placeholder:text-muted',
  'transition-[border-color] duration-150',
  'hover:border-border-hover',
  'disabled:pointer-events-none disabled:opacity-50',
)

export function Input({
  size = 'md',
  className,
  ...rest
}: { size?: ControlSize } & Omit<InputHTMLAttributes<HTMLInputElement>, 'size'>) {
  return (
    <input
      className={cx(FIELD, size === 'sm' ? 'h-7 px-2 text-xs' : 'h-9 px-2.5 text-sm', className)}
      {...rest}
    />
  )
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea className={cx(FIELD, 'px-2.5 py-2 text-sm leading-relaxed', className)} {...rest} />
  )
}

export function Select({
  size = 'md',
  className,
  children,
  ...rest
  // `size` is a native select attribute meaning "how many rows to show", so
  // ours has to displace it rather than merge with it.
}: { size?: ControlSize } & Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'>) {
  return (
    <select
      className={cx(FIELD, size === 'sm' ? 'h-7 px-1.5 text-xs' : 'h-9 px-2 text-sm', className)}
      {...rest}
    >
      {children}
    </select>
  )
}

/**
 * A labelled field.
 *
 * Label above, hint below — in that order because the hint is read after
 * the control has been looked at, and a hint between the two pushes the
 * label away from the thing it names.
 */
export function Field({
  label,
  hint,
  htmlFor,
  className,
  children,
}: {
  label: string
  hint?: ReactNode
  htmlFor?: string
  className?: string
  children: ReactNode
}) {
  const Wrapper = htmlFor ? 'div' : 'label'
  return (
    <Wrapper className={cx('flex flex-col gap-1.5', className)}>
      <label htmlFor={htmlFor} className="text-xs font-medium text-slate">
        {label}
      </label>
      {children}
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </Wrapper>
  )
}

/* ── Segmented control ─────────────────────────────────────────────────── */

/**
 * A small set of exclusive options, shown rather than hidden in a dropdown.
 *
 * Used where there are two to four choices and the current one is worth
 * seeing without opening anything: week/month, grid/list, how many. More
 * than four and it should be a Select.
 */
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
  size = 'md',
  className,
}: {
  value: T
  options: ReadonlyArray<{ value: T; label: ReactNode; title?: string }>
  onChange: (value: T) => void
  /** Names the group for a screen reader, and disambiguates in tests. */
  label: string
  size?: ControlSize
  className?: string
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cx(
        'inline-flex rounded-sm border border-border bg-page p-0.5',
        'transition-[border-color] duration-150 hover:border-border-hover',
        className,
      )}
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={String(option.value)}
            type="button"
            aria-pressed={selected}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={cx(
              'inline-flex items-center justify-center gap-1.5 rounded-[3px] whitespace-nowrap',
              'transition-[background-color,color] duration-150',
              size === 'sm' ? 'h-6 px-2 text-xs' : 'h-8 px-3 text-sm',
              selected ? 'bg-card text-ink shadow-card' : 'text-slate hover:text-ink',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

/* ── Tabs ──────────────────────────────────────────────────────────────── */

/**
 * A row of tabs over one panel.
 *
 * Underline rather than a filled pill: the Desk is a reading surface and a
 * row of filled pills at the top of it competes with the headline below.
 * The active tab is the only chilli on the panel, which is the same job
 * the accent does in the sidebar.
 *
 * Deliberately not routed. A tab here is which face of one topic you are
 * looking at, not a place — putting it in the URL would mean the back
 * button walks through four views of the same thing.
 */
export function Tabs<T extends string>({
  value,
  tabs,
  onChange,
  label,
  className,
}: {
  value: T
  tabs: ReadonlyArray<{ value: T; label: string; count?: number; disabled?: boolean }>
  onChange: (value: T) => void
  label: string
  className?: string
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className={cx('flex gap-1 border-b border-border', className)}
      onKeyDown={(event) => {
        const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
        if (step === 0) return
        event.preventDefault()
        const enabled = tabs.filter((t) => !t.disabled)
        const here = enabled.findIndex((t) => t.value === value)
        const next = enabled[(here + step + enabled.length) % enabled.length]
        if (next) onChange(next.value)
      }}
    >
      {tabs.map((tab) => {
        const selected = tab.value === value
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={selected}
            disabled={tab.disabled}
            // Only the selected tab is in the tab order; the arrow keys
            // move between them, which is how a tablist is meant to work.
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.value)}
            className={cx(
              'relative -mb-px flex items-center gap-1.5 px-3 py-2 text-sm whitespace-nowrap',
              'transition-colors duration-150',
              'disabled:pointer-events-none disabled:opacity-40',
              selected
                ? 'border-b-2 border-chilli text-ink'
                : 'border-b-2 border-transparent text-slate hover:text-ink',
            )}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 ? (
              <span className="num text-xs text-muted">{tab.count}</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

/* ── Labels and small text ─────────────────────────────────────────────── */

/**
 * A small capsule naming a source, a status or a category.
 *
 * `tone` exists because a status chip and a category chip are different
 * claims: one is a signal and one is a label. Only the signals get colour.
 */
export type ChipTone = 'neutral' | 'rising' | 'falling' | 'watch' | 'solid'

const CHIP_TONE: Record<ChipTone, string> = {
  neutral: 'border-border text-slate',
  rising: 'border-chilli/40 text-chilli',
  falling: 'border-neem/40 text-neem',
  watch: 'border-turmeric/40 text-turmeric',
  solid: 'border-transparent bg-overlay text-ink',
}

export function Chip({
  tone = 'neutral',
  children,
  className,
  title,
}: {
  tone?: ChipTone
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center rounded-sm border px-1.5 py-px text-xs leading-5 whitespace-nowrap',
        CHIP_TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

/** Section heading: sentence case, slate, 12px. Not an all-caps eyebrow. */
export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <h2 className={cx('text-xs font-medium text-slate', className)}>{children}</h2>
}

/** Inline code, used in hints that name a command or a variable. */
export function Code({ children }: { children: ReactNode }) {
  return (
    <code className="rounded-sm border border-border bg-page px-1 py-px font-mono text-xs text-ink">
      {children}
    </code>
  )
}

/**
 * One cell of a meta row: a label above its value.
 *
 * On a wide layout the cells sit on one line divided by hairline rules, so
 * the group reads as a single sentence of facts rather than four boxes. The
 * rules are dropped when the row wraps, where a leading rule on the wrapped
 * cell is an orphan.
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
    <div className="desk:pr-5 desk:pl-5 desk:first:pl-0 desk:last:pr-0 desk:not-first:border-l flex flex-col gap-0.5 border-border">
      <span className="text-xs text-slate">{label}</span>
      <span className={cx('text-sm text-ink', numeric && 'num')}>{children}</span>
    </div>
  )
}
