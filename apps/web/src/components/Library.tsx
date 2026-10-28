'use client'

import type { EditorialStatus, LibraryFacets, LibraryItem, LibraryPage } from '@trendforge/types'
import { EDITORIAL_LABELS, EDITORIAL_STATUSES } from '@trendforge/types'
import Link from 'next/link'
import { useCallback, useEffect, useRef, useState, useTransition } from 'react'

import { Chip, Empty, SectionLabel, cx } from '@/components/ui'
import { formatAge, formatIstDateTime } from '@/lib/format'
import { type LibraryFilters, fetchLibrary, moveJob } from '@/lib/library'

/**
 * Everything this workspace has generated.
 *
 * A ladder, not a gallery. The board taught the user to read a dense
 * left-aligned list separated by dotted rules, and the library is the same
 * material a day later — so it is the same shape, with a thumbnail where
 * the rank numeral would be. Cards are reserved for the asset previews
 * inside an item, per CLAUDE.md.
 *
 * The first page is rendered on the server. Filtering refetches here rather
 * than navigating: a filter change is not a new page, and pushing one would
 * put forty near-identical entries in the back button.
 */

const PAGE = 50

export function Library({ initial, facets }: { initial: LibraryPage; facets: LibraryFacets }) {
  const [page, setPage] = useState(initial)
  const [filters, setFilters] = useState<LibraryFilters>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, startLoading] = useTransition()
  // Guards against an older request landing after a newer one and showing
  // the previous filter's results.
  const request = useRef(0)

  const load = useCallback(
    async (next: LibraryFilters, offset = 0) => {
      const ticket = ++request.current
      setError(null)
      try {
        const body = await fetchLibrary({ ...next, limit: PAGE, offset })
        if (ticket !== request.current) return
        setPage(offset === 0 ? body : { ...body, items: [...page.items, ...body.items] })
      } catch (cause) {
        if (ticket !== request.current) return
        setError(cause instanceof Error ? cause.message : 'Could not reach the API.')
      }
    },
    // page.items only, not the whole page: appending reads the current
    // items, and depending on the object would rebuild this on every load.
    [page.items],
  )

  const apply = (change: Partial<LibraryFilters>) => {
    const next = { ...filters, ...change }
    for (const key of Object.keys(next) as Array<keyof LibraryFilters>) {
      if (next[key] === undefined || next[key] === '') delete next[key]
    }
    setFilters(next)
    startLoading(() => void load(next))
  }

  /** After moving an item, so counts and a status filter stay honest. */
  const reload = () => startLoading(() => void load(filters))

  return (
    <>
      <Filters facets={facets} filters={filters} onChange={apply} />

      <section className="mt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <SectionLabel>
            {page.total === 0
              ? 'Nothing yet'
              : page.items.length < page.total
                ? `${page.items.length} of ${page.total} items`
                : `${page.total} ${page.total === 1 ? 'item' : 'items'}`}
          </SectionLabel>
          {loading ? <span className="text-xs text-slate">Loading…</span> : null}
          {error ? (
            <span role="alert" className="text-xs text-chilli">
              {error}
            </span>
          ) : null}
        </div>

        {page.items.length === 0 ? (
          <div className="mt-4">
            <Empty
              title={
                Object.keys(filters).length > 0
                  ? 'Nothing matches those filters.'
                  : 'No posts or reels yet.'
              }
              hint={
                Object.keys(filters).length > 0 ? (
                  <button
                    type="button"
                    onClick={() => apply(cleared(filters))}
                    className="underline underline-offset-2"
                  >
                    Clear the filters
                  </button>
                ) : (
                  <>
                    Open a topic on the{' '}
                    <Link href="/" className="text-ink underline underline-offset-2">
                      board
                    </Link>{' '}
                    and generate a post.
                  </>
                )
              }
            />
          </div>
        ) : (
          <ul className="mt-4">
            {page.items.map((item) => (
              <Row key={item.id} item={item} onMoved={reload} />
            ))}
          </ul>
        )}

        {page.items.length < page.total ? (
          <button
            type="button"
            onClick={() => startLoading(() => void load(filters, page.items.length))}
            className="mt-6 border border-border px-3 py-1.5 text-sm text-slate hover:text-ink"
          >
            Show {Math.min(PAGE, page.total - page.items.length)} more
          </button>
        ) : null}
      </section>
    </>
  )
}

/** Every key set back to undefined, which `apply` then deletes. */
function cleared(filters: LibraryFilters): Partial<LibraryFilters> {
  return Object.fromEntries(Object.keys(filters).map((key) => [key, undefined]))
}

function Row({ item, onMoved }: { item: LibraryItem; onMoved: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function move(status: EditorialStatus) {
    setBusy(true)
    setError(null)
    try {
      // Scheduling needs a time, and the calendar is where a time is
      // chosen. From here it goes to tomorrow morning, which is the
      // commonest answer and is one drag away from any other.
      const scheduled_at = status === 'scheduled' ? tomorrowMorning() : undefined
      await moveJob(item.id, {
        editorial_status: status,
        ...(scheduled_at ? { scheduled_at } : {}),
      })
      onMoved()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update this item.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="flex flex-wrap items-start gap-x-5 gap-y-3 border-b border-dotted border-rule py-4">
      <Thumbnail item={item} />

      <div className="min-w-0 flex-1">
        <Link
          // Back to the Desk, on the board this topic sits on, with the
          // topic selected — which is where every action on an item lives.
          href={`/?region=${item.region_code}&topic=${item.trend_id}`}
          className="block text-base text-ink hover:underline hover:underline-offset-2"
        >
          {item.hook ?? item.topic}
        </Link>
        {/* Only when it adds something. A failed job has no caption, so the
            hook falls back to the topic and printing both would be the same
            line twice. */}
        {item.hook && item.hook !== item.topic ? (
          <p className="mt-0.5 truncate text-sm text-slate">{item.topic}</p>
        ) : null}
        <p className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate">
          <span>{item.brand_name}</span>
          <span>{item.region_name}</span>
          <span className="capitalize">{item.language}</span>
          <span>{item.kind === 'reel' ? 'Reel' : 'Post'}</span>
          <span>{formatAge(item.created_at)}</span>
          {item.scheduled_at ? (
            <span className="text-ink">For {formatIstDateTime(item.scheduled_at)}</span>
          ) : null}
        </p>
        {item.status === 'failed' ? (
          // Clamped: a model-chain failure names eight models and runs to
          // four lines, which on a dense list buries every row after it.
          // The full text is one hover away and is in the Desk.
          <p title={item.error ?? undefined} className="mt-1.5 line-clamp-2 text-xs text-chilli">
            {item.error ?? 'This job failed.'}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="mt-1.5 text-xs text-chilli">
            {error}
          </p>
        ) : null}
      </div>

      <StatusPicker value={item.editorial_status} busy={busy} onPick={move} />
    </li>
  )
}

function Thumbnail({ item }: { item: LibraryItem }) {
  if (!item.preview_url) {
    return (
      <span className="flex h-16 w-16 shrink-0 items-center justify-center border border-border text-xs text-slate">
        {item.status === 'failed' ? 'Failed' : item.status === 'ready' ? 'No image' : 'Running'}
      </span>
    )
  }
  return (
    /* A MinIO URL on a published port, which next/image cannot be configured
       for without pinning the dev host into next.config. Always an image —
       a reel's preview is its poster frame, not the mp4. */
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={item.preview_url}
      alt=""
      className="h-16 w-16 shrink-0 border border-border object-cover"
      loading="lazy"
    />
  )
}

/**
 * The four states as a row of buttons rather than a select.
 *
 * There are four, they are an order, and the current one is worth seeing
 * without opening anything — which is three reasons a dropdown is the wrong
 * control. The selected one is the only filled thing on the row.
 */
function StatusPicker({
  value,
  busy,
  onPick,
}: {
  value: EditorialStatus
  busy: boolean
  onPick: (status: EditorialStatus) => void
}) {
  return (
    <div className="flex shrink-0 flex-wrap gap-px" role="group" aria-label="Status">
      {EDITORIAL_STATUSES.map((status) => {
        const current = status === value
        return (
          <button
            key={status}
            type="button"
            disabled={busy || current}
            aria-pressed={current}
            onClick={() => onPick(status)}
            className={cx(
              'border px-2 py-1 text-xs',
              current
                ? 'border-ink bg-ink text-page'
                : 'border-border text-slate hover:text-ink disabled:opacity-40',
            )}
          >
            {EDITORIAL_LABELS[status]}
          </button>
        )
      })}
    </div>
  )
}

function Filters({
  facets,
  filters,
  onChange,
}: {
  facets: LibraryFacets
  filters: LibraryFilters
  onChange: (change: Partial<LibraryFilters>) => void
}) {
  const [q, setQ] = useState('')

  // Typing should not fire a request per keystroke, and an explicit submit
  // for one field beside eight live ones would be inconsistent.
  useEffect(() => {
    const timer = setTimeout(() => onChange({ q: q || undefined }), 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const active = Object.keys(filters).filter((key) => key !== 'limit' && key !== 'offset').length

  return (
    <div className="mt-6 border-t border-border pt-5">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate">Search topics</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="cricket"
            className={INPUT}
          />
        </label>

        <Select
          label="Brand"
          value={filters.brand_id ? String(filters.brand_id) : ''}
          onChange={(value) => onChange({ brand_id: value ? Number(value) : undefined })}
          options={facets.brands.map((b) => ({
            value: String(b.id),
            label: `${b.name} (${b.count})`,
          }))}
          all="All brands"
        />

        <Select
          label="Region"
          value={filters.region ?? ''}
          onChange={(value) => onChange({ region: value || undefined })}
          options={facets.regions.map((r) => ({
            value: String(r.code),
            label: `${r.name} (${r.count})`,
          }))}
          all="Everywhere"
        />

        <Select
          label="Language"
          value={filters.language ?? ''}
          onChange={(value) => onChange({ language: value || undefined })}
          options={facets.languages.map((l) => ({ value: l, label: capitalise(l) }))}
          all="Any language"
        />

        <Select
          label="Format"
          value={filters.format ?? ''}
          onChange={(value) => onChange({ format: value || undefined })}
          options={facets.formats.map((f) => ({ value: f, label: capitalise(f) }))}
          all="Any format"
        />

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate">Made since</span>
          <input
            type="date"
            value={filters.created_from?.slice(0, 10) ?? ''}
            onChange={(e) =>
              onChange({
                // Midnight IST, not UTC: "since 27 Oct" means the Indian
                // day, and a UTC midnight would include 05:30 of the day
                // before.
                created_from: e.target.value ? `${e.target.value}T00:00:00+05:30` : undefined,
              })
            }
            className={INPUT}
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {/* Grouped and named: the four status words appear again on every
            row, and without this neither a screen reader nor a test can
            tell "filter to approved" from "approve this item". */}
        <span className="flex flex-wrap items-center gap-2" role="group" aria-label="Kind filter">
          <Chip>
            <button
              type="button"
              onClick={() => onChange({ kind: undefined })}
              className={filters.kind ? 'text-slate' : 'text-ink'}
            >
              Everything
            </button>
          </Chip>
          {(['post', 'reel'] as const).map((kind) => (
            <Chip key={kind}>
              <button
                type="button"
                onClick={() => onChange({ kind })}
                className={filters.kind === kind ? 'text-ink' : 'text-slate'}
              >
                {kind === 'post' ? 'Posts' : 'Reels'}
              </button>
            </Chip>
          ))}
        </span>

        <span className="mx-2 h-4 w-px bg-rule" aria-hidden="true" />

        <span className="flex flex-wrap items-center gap-2" role="group" aria-label="Status filter">
          {EDITORIAL_STATUSES.map((status) => (
            <Chip key={status}>
              <button
                type="button"
                onClick={() => onChange({ status: filters.status === status ? undefined : status })}
                className={filters.status === status ? 'text-ink' : 'text-slate'}
              >
                {EDITORIAL_LABELS[status]}
              </button>
            </Chip>
          ))}
        </span>

        {active > 0 ? (
          <button
            type="button"
            onClick={() => onChange(cleared(filters))}
            className="ml-2 text-xs text-slate underline underline-offset-2 hover:text-ink"
          >
            Clear {active} {active === 1 ? 'filter' : 'filters'}
          </button>
        ) : null}
      </div>
    </div>
  )
}

function Select({
  label,
  value,
  onChange,
  options,
  all,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: Array<{ value: string; label: string }>
  all: string
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-slate">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={options.length === 0}
        className={INPUT}
      >
        <option value="">{all}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

const capitalise = (value: string) => value.charAt(0).toUpperCase() + value.slice(1)

/** Tomorrow at 09:00 IST, as an instant. */
function tomorrowMorning(): string {
  const now = new Date()
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  const day = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(tomorrow)
  return `${day}T09:00:00+05:30`
}

const INPUT = 'border border-border bg-card px-2 py-1.5 text-sm text-ink'
