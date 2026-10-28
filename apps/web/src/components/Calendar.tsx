'use client'

import type { LibraryItem } from '@trendforge/types'
import { Film, Image as ImageIcon } from 'lucide-react'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { EmptyState } from '@/components/Empty'
import { Button, Card, SectionLabel, Segmented, cx } from '@/components/ui'
import {
  type CalendarView,
  WEEKDAYS,
  addDays,
  addMonths,
  at,
  byDay,
  dayLabel,
  gridFor,
  monthLabel,
  spokenDate,
  startOfMonth,
  startOfWeek,
  today,
  weekLabel,
  windowFor,
} from '@/lib/calendar'
import { formatIstTime, istDayKey } from '@/lib/format'
import { fetchLibrary, moveJob } from '@/lib/library'

/**
 * What is scheduled, and when.
 *
 * Nothing publishes yet — a scheduled item carries a time and that is all
 * it carries. The calendar is where that time is decided, which is why it
 * is worth building before there is anything to publish to: deciding when
 * forty posts go out is the work, and doing it in a list of timestamps is
 * the thing a calendar exists to replace.
 *
 * Dates are IST day strings throughout, not Date objects — see lib/calendar.
 *
 * Moving an item works two ways on purpose. Dragging is what a mouse
 * expects; arrow keys with the item focused is what the keyboard needs, and
 * CLAUDE.md asks for a keyboard-navigable surface rather than one with a
 * mouse-only action in it.
 */

/** A month is 42 cells; nothing sensible fills them past this. */
const WINDOW_LIMIT = 200

export function Calendar({ initialItems }: { initialItems: LibraryItem[] }) {
  const [view, setView] = useState<CalendarView>('month')
  const [anchor, setAnchor] = useState(() => today())
  const [items, setItems] = useState(initialItems)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  /** What the last move did, for the live region. */
  const [announcement, setAnnouncement] = useState('')
  const request = useRef(0)

  const days = useMemo(() => gridFor(view, anchor), [view, anchor])
  const scheduled = useMemo(() => byDay(items), [items])
  const now = today()

  const load = useCallback(async (grid: string[]) => {
    const ticket = ++request.current
    const { from, to } = windowFor(grid)
    try {
      const page = await fetchLibrary({
        status: 'scheduled',
        scheduled_from: from,
        scheduled_to: to,
        limit: WINDOW_LIMIT,
      })
      if (ticket !== request.current) return
      setItems(page.items)
      setError(null)
    } catch (cause) {
      if (ticket !== request.current) return
      setError(cause instanceof Error ? cause.message : 'Could not reach the API.')
    }
  }, [])

  // The first window is server-rendered; every later one is fetched. Skipped
  // on mount so the page does not immediately refetch what it was given.
  const mounted = useRef(false)
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true
      return
    }
    void load(days)
  }, [days, load])

  /**
   * Move an item to another day, keeping its time of day.
   *
   * Optimistic: the grid redraws before the PATCH lands and rolls back if
   * it fails. A drag that visibly does nothing for 200ms feels broken, and
   * this is the one interaction on the page.
   */
  async function move(item: LibraryItem, day: string) {
    const previous = items
    const when = at(day, item.scheduled_at)
    setItems((current) =>
      current.map((row) => (row.id === item.id ? { ...row, scheduled_at: when } : row)),
    )
    setAnnouncement(`${item.hook ?? item.topic} moved to ${spokenDate(day)}`)
    setBusy(true)
    setError(null)

    try {
      await moveJob(item.id, { scheduled_at: when })
    } catch (cause) {
      setItems(previous)
      setAnnouncement('')
      setError(cause instanceof Error ? cause.message : 'Could not move this item.')
    } finally {
      setBusy(false)
    }
  }

  const step = (direction: 1 | -1) =>
    setAnchor((current) =>
      view === 'week'
        ? addDays(current, 7 * direction)
        : addMonths(startOfMonth(current), direction),
    )

  return (
    <>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-border pt-5">
        <div className="flex items-baseline gap-4">
          <h2 className="font-display text-xl font-bold text-ink">
            {view === 'week' ? weekLabel(days) : monthLabel(anchor)}
          </h2>
          <button
            type="button"
            onClick={() => setAnchor(today())}
            className="text-xs text-slate underline underline-offset-2 hover:text-ink"
          >
            Today
          </button>
        </div>

        <div className="flex items-center gap-4">
          <Segmented
            label="View"
            size="sm"
            value={view}
            onChange={(option) => {
              setView(option)
              setAnchor((current) =>
                option === 'week' ? startOfWeek(current) : startOfMonth(current),
              )
            }}
            options={[
              { value: 'week' as const, label: 'Week' },
              { value: 'month' as const, label: 'Month' },
            ]}
          />

          <div className="flex gap-1.5">
            <Button
              size="sm"
              onClick={() => step(-1)}
              aria-label={view === 'week' ? 'Previous week' : 'Previous month'}
            >
              Back
            </Button>
            <Button
              size="sm"
              onClick={() => step(1)}
              aria-label={view === 'week' ? 'Next week' : 'Next month'}
            >
              Next
            </Button>
          </div>
        </div>
      </div>

      <p className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate">
        <span>
          {items.length === 0
            ? 'Nothing scheduled in this window'
            : `${items.length} scheduled ${items.length === 1 ? 'item' : 'items'}`}
        </span>
        {/* The agenda below the Desk breakpoint has no drop target, so it
            must not promise one. */}
        <span className="desk:inline hidden">
          Drag an item to another day, or focus it and use the arrow keys.
        </span>
        <span className="desk:hidden">Scheduled times, in order. Change one from the library.</span>
        {busy ? <span>Saving…</span> : null}
        {error ? (
          <span role="alert" className="text-chilli">
            {error}
          </span>
        ) : null}
      </p>

      {/* Announced rather than only drawn: a keyboard move changes a cell
          the user may not be looking at. */}
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {/*
       * Two renderings of one window, switched in CSS rather than by
       * measuring the viewport — a hook that reads window.innerWidth
       * disagrees with the server on the first paint, and a calendar that
       * flickers between two shapes on load is worse than either.
       *
       * Seven columns at 390px gives each day 48 pixels, which truncates
       * every title to about three characters. Below the Desk breakpoint
       * the days that have something on them are listed instead, which is
       * what a phone calendar is.
       */}
      <div className="desk:block hidden">
        <Grid
          days={days}
          view={view}
          today={now}
          anchorMonth={anchor.slice(0, 7)}
          scheduled={scheduled}
          onMove={move}
        />
      </div>
      <div className="desk:hidden">
        <Agenda days={days} today={now} scheduled={scheduled} onMove={move} />
      </div>

      {items.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            art="calendar"
            title="Nothing scheduled in this window."
            hint={
              <>
                Pick items in the{' '}
                <Link href="/library" className="text-ink underline underline-offset-2">
                  library
                </Link>{' '}
                and set them to Scheduled.
              </>
            }
          />
        </div>
      ) : null}
    </>
  )
}

function Grid({
  days,
  view,
  today: now,
  anchorMonth,
  scheduled,
  onMove,
}: {
  days: string[]
  view: CalendarView
  today: string
  anchorMonth: string
  scheduled: Map<string, LibraryItem[]>
  onMove: (item: LibraryItem, day: string) => void
}) {
  const [over, setOver] = useState<string | null>(null)

  return (
    <div className="mt-5">
      <div className="grid grid-cols-7 border-b border-border pb-1.5">
        {WEEKDAYS.map((name) => (
          <SectionLabel key={name}>{name}</SectionLabel>
        ))}
      </div>

      <div className="grid grid-cols-7">
        {days.map((day) => {
          const items = scheduled.get(day) ?? []
          const outside = view === 'month' && !day.startsWith(anchorMonth)
          return (
            <div
              key={day}
              onDragOver={(e) => {
                // Without preventDefault the browser refuses the drop, and
                // the cursor says "no" over every cell.
                e.preventDefault()
                setOver(day)
              }}
              onDragLeave={() => setOver((current) => (current === day ? null : current))}
              onDrop={(e) => {
                e.preventDefault()
                setOver(null)
                const id = Number(e.dataTransfer.getData('text/plain'))
                const item = [...scheduled.values()].flat().find((row) => row.id === id)
                if (item && day !== dayOf(item)) onMove(item, day)
              }}
              className={cx(
                'min-h-28 border-r border-b border-border p-1.5 last:border-r-0',
                view === 'week' && 'min-h-56',
                outside && 'opacity-45',
                // Today is a ground, not just a coloured numeral: on a
                // 42-cell month grid one chilli glyph is easy to miss.
                day === now && 'bg-chilli/5',
                over === day && 'bg-row-active',
              )}
            >
              <div className="flex items-baseline justify-between">
                {/* The folio numeral, as on the ladder: display face,
                    hanging at the top of its column. */}
                <span
                  className={cx('rank-numeral text-lg', day === now ? 'text-chilli' : 'text-ink')}
                >
                  {dayLabel(day)}
                </span>
                {items.length > 2 ? (
                  <span className="num text-xs text-slate">{items.length}</span>
                ) : null}
              </div>

              <ul className="mt-1.5 flex flex-col gap-1">
                {items.map((item) => (
                  <Item key={item.id} item={item} onMove={onMove} />
                ))}
              </ul>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * The phone rendering: only the days that have something on them.
 *
 * No drag target — dragging across a scrolling list on a touch screen is a
 * fight, and the arrow keys are still here for a keyboard. Rescheduling on
 * a phone is better served by the library's status buttons than by a
 * gesture that works badly.
 */
function Agenda({
  days,
  today: now,
  scheduled,
  onMove,
}: {
  days: string[]
  today: string
  scheduled: Map<string, LibraryItem[]>
  onMove: (item: LibraryItem, day: string) => void
}) {
  const filled = days.filter((day) => (scheduled.get(day)?.length ?? 0) > 0)

  return (
    <div className="mt-5">
      {filled.map((day) => (
        <section key={day} className="border-b border-dotted border-rule py-4 first:border-t">
          <h3 className="flex items-baseline gap-2">
            <span className={cx('rank-numeral text-xl', day === now ? 'text-chilli' : 'text-ink')}>
              {dayLabel(day)}
            </span>
            <span className="text-sm text-slate">{spokenDate(day)}</span>
          </h3>
          <ul className="mt-2 flex flex-col gap-2">
            {(scheduled.get(day) ?? []).map((item) => (
              <Item key={item.id} item={item} onMove={onMove} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

/** The IST day an item sits on — not `slice(0, 10)`, which is the UTC one
 *  and is a day out for anything scheduled before 05:30 IST. */
const dayOf = (item: LibraryItem) => (item.scheduled_at ? istDayKey(item.scheduled_at) : '')

function Item({
  item,
  onMove,
}: {
  item: LibraryItem
  onMove: (item: LibraryItem, day: string) => void
}) {
  const title = item.hook ?? item.topic
  const time = item.scheduled_at ? formatIstTime(item.scheduled_at) : ''

  /** Left and right move a day, up and down a week — the grid's own shape. */
  function onKeyDown(event: React.KeyboardEvent) {
    const steps: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
    }
    const step = steps[event.key]
    if (step === undefined || !item.scheduled_at) return
    // Or the browser scrolls the page under the user instead.
    event.preventDefault()
    onMove(item, addDays(istDayKey(item.scheduled_at), step))
  }

  return (
    <li className="group relative">
      <Card className="overflow-hidden border-l-2 border-l-ink transition-[border-color] duration-150 focus-within:border-border-hover hover:border-border-hover">
        {/*
         * A real button, not a div with role="button". It was the latter
         * first, with the brand-name link inside it — which is invalid (a
         * link inside a button is not reachable as either) and which cost
         * the element its native keyboard behaviour. The link is a sibling.
         */}
        <button
          type="button"
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData('text/plain', String(item.id))
            e.dataTransfer.effectAllowed = 'move'
          }}
          onKeyDown={onKeyDown}
          aria-label={`${title}, ${time}. Use the arrow keys to move it.`}
          className="flex w-full cursor-grab gap-1.5 p-1 text-left active:cursor-grabbing"
        >
          <Thumb item={item} />
          <span className="min-w-0 flex-1">
            <span className="num block text-xs text-slate">{time}</span>
            <span className="line-clamp-2 block text-xs text-ink">{title}</span>
          </span>
        </button>
        <Link
          href={`/board?region=${item.region_code}&topic=${item.trend_id}`}
          className="block truncate px-1.5 pb-1 text-[11px] text-muted hover:text-ink"
          // Or dragging the item would start a link drag instead.
          draggable={false}
        >
          {item.brand_name}
        </Link>
      </Card>

      {/*
       * The caption, on hover.
       *
       * A day cell is 150px wide and a title is clamped to two lines, so
       * the commonest question on this page — "which post is this" —
       * cannot be answered from the grid alone. This is the answer, in a
       * popover that is not clickable and does not move anything: it
       * exists so you can decide whether to drag, not so you can act in it.
       *
       * Pointer-events are off so it never swallows the drag that starts
       * underneath it.
       */}
      <div
        role="tooltip"
        className={cx(
          'pointer-events-none absolute top-0 left-full z-20 ml-2 hidden w-60 rounded-md',
          'border border-border bg-overlay p-2.5 shadow-overlay',
          'desk:group-hover:block desk:group-focus-within:block',
        )}
      >
        <p className="text-xs text-ink">{title}</p>
        {item.hook && item.hook !== item.topic ? (
          <p className="mt-1 text-xs text-slate">{item.topic}</p>
        ) : null}
        <p className="mt-1.5 flex flex-wrap gap-x-2 text-xs text-muted">
          <span>{item.brand_name}</span>
          <span>{item.region_name}</span>
          <span className="capitalize">{item.language}</span>
          <span>{item.kind === 'reel' ? 'Reel' : 'Post'}</span>
        </p>
      </div>
    </li>
  )
}

/** The poster, small. Always a still — a <video> draws nothing until it
 *  has fetched a frame, so the API hands over a reel's poster instead. */
function Thumb({ item }: { item: LibraryItem }) {
  if (!item.preview_url) {
    return (
      <span className="flex size-9 shrink-0 items-center justify-center rounded-sm border border-border bg-page text-muted">
        {item.kind === 'reel' ? (
          <Film aria-hidden="true" className="size-3.5" strokeWidth={2} />
        ) : (
          <ImageIcon aria-hidden="true" className="size-3.5" strokeWidth={2} />
        )}
      </span>
    )
  }
  return (
    /* A MinIO URL on a published port, which next/image cannot be
       configured for without pinning the dev host into next.config. */
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={item.preview_url}
      alt=""
      loading="lazy"
      className="size-9 shrink-0 rounded-sm border border-border object-cover"
    />
  )
}
