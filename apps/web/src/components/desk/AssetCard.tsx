'use client'

import { CalendarPlus, Check, Download, ExternalLink } from 'lucide-react'
import { useState } from 'react'

import { Card, cx } from '@/components/ui'
import { moveJob } from '@/lib/library'

/**
 * A generated asset, as a card you can act on.
 *
 * The actions appear on hover and on focus, over the asset rather than
 * beside it: three buttons permanently under every thumbnail is three
 * buttons of furniture per card, and on a grid of six that is eighteen
 * controls competing with the work they belong to.
 *
 * Hover is not the only way in. The overlay is also shown when anything
 * inside the card has focus, so the keyboard reaches every action without
 * a pointer — which is the half of "hover reveals actions" that usually
 * gets forgotten.
 */

export type AssetAction = 'open' | 'save' | 'schedule'

export function AssetCard({
  url,
  title,
  subtitle,
  jobId,
  children,
  onScheduled,
}: {
  /** The file itself, for open and save. Null while a job is still running. */
  url: string | null
  title: string
  subtitle?: string
  /** Which job this came from, for scheduling. */
  jobId?: number
  /** The preview — an <img>, a <video>, or a placeholder. */
  children: React.ReactNode
  onScheduled?: () => void
}) {
  const [scheduled, setScheduled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function schedule() {
    if (!jobId) return
    setBusy(true)
    setError(null)
    try {
      // Tomorrow at nine, the same default the library uses. The calendar
      // is where a different time gets chosen, and it is one drag away.
      await moveJob(jobId, { editorial_status: 'scheduled', scheduled_at: tomorrowMorning() })
      setScheduled(true)
      onScheduled?.()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not schedule this.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <figure className="min-w-0">
      {/* `group` and `focus-within` together: the overlay answers a pointer
          and a tab key identically. */}
      <Card className="group relative overflow-hidden focus-within:border-border-hover hover:border-border-hover">
        {children}

        {url ? (
          <div
            className={cx(
              'absolute inset-x-0 bottom-0 flex items-center gap-1 p-1.5',
              // A wash rather than a solid bar, so the bottom of the asset
              // is still visible under its own actions.
              'bg-gradient-to-t from-page/95 to-transparent pt-8',
              'opacity-0 transition-opacity duration-150',
              'group-hover:opacity-100 group-focus-within:opacity-100',
            )}
          >
            <Action
              as="a"
              href={url}
              target="_blank"
              rel="noreferrer"
              label="Open full size"
              icon={<ExternalLink aria-hidden="true" className="size-3.5" strokeWidth={2} />}
            />
            <Action
              as="a"
              href={url}
              download
              label="Save"
              icon={<Download aria-hidden="true" className="size-3.5" strokeWidth={2} />}
            />
            {jobId ? (
              <Action
                as="button"
                onClick={schedule}
                disabled={busy || scheduled}
                label={scheduled ? 'Scheduled for tomorrow' : 'Schedule for tomorrow'}
                icon={
                  scheduled ? (
                    <Check aria-hidden="true" className="size-3.5" strokeWidth={2} />
                  ) : (
                    <CalendarPlus aria-hidden="true" className="size-3.5" strokeWidth={2} />
                  )
                }
              />
            ) : null}
          </div>
        ) : null}
      </Card>

      <figcaption className="mt-1.5 flex items-baseline justify-between gap-2">
        <span className="truncate text-xs text-ink">{title}</span>
        {subtitle ? <span className="num shrink-0 text-xs text-muted">{subtitle}</span> : null}
      </figcaption>
      {error ? (
        <p role="alert" className="mt-1 text-xs text-chilli">
          {error}
        </p>
      ) : null}
      {/* Announced rather than only drawn: the icon swapping to a tick is
          invisible to a screen reader. */}
      <span aria-live="polite" className="sr-only">
        {scheduled ? `${title} scheduled for tomorrow morning` : ''}
      </span>
    </figure>
  )
}

/**
 * One action. A link or a button depending on what it does — opening and
 * saving are navigations and scheduling is a write, and making all three
 * buttons would mean reimplementing download in JavaScript.
 */
function Action(
  props:
    | ({ as: 'a'; label: string; icon: React.ReactNode } & React.AnchorHTMLAttributes<HTMLAnchorElement>)
    | ({ as: 'button'; label: string; icon: React.ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>),
) {
  const { as, label, icon, ...rest } = props
  const className = cx(
    'inline-flex size-7 items-center justify-center rounded-sm',
    'border border-border bg-overlay text-slate shadow-card',
    'transition-colors duration-150',
    'hover:border-border-hover hover:text-ink',
    'active:translate-y-px',
    'disabled:pointer-events-none disabled:opacity-50',
  )

  if (as === 'a') {
    return (
      <a
        {...(rest as React.AnchorHTMLAttributes<HTMLAnchorElement>)}
        aria-label={label}
        title={label}
        className={className}
      >
        {icon}
      </a>
    )
  }
  return (
    <button
      type="button"
      {...(rest as React.ButtonHTMLAttributes<HTMLButtonElement>)}
      aria-label={label}
      title={label}
      className={className}
    >
      {icon}
    </button>
  )
}

/** Tomorrow at 09:00 IST, as an instant. */
function tomorrowMorning(): string {
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
  const day = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(tomorrow)
  return `${day}T09:00:00+05:30`
}
