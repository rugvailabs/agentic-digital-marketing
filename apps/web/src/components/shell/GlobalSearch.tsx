'use client'

import { Search } from 'lucide-react'
import Link from 'next/link'
import { useEffect, useId, useRef, useState } from 'react'

import { Chip, cx } from '@/components/house'

/**
 * One box across topics, brands and generated work.
 *
 * A marketer with a name in their head had three places to go and look: a
 * topic behind a board they have to pick first, a post behind four library
 * filters, a brand on a settings page. This is so that knowing the name is
 * enough.
 *
 * Results are a panel below the field rather than a modal. A modal would
 * mean the thing you were looking at disappears while you search for the
 * thing next to it, and this is a product where you are usually comparing.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

/** Long enough to outlast typing, short enough not to feel posted. */
const DEBOUNCE_MS = 180

type TopicHit = {
  trend_id: number
  topic: string
  region_code: string
  region_name: string
  rank: number
  also_on: number
}
type BrandHit = {
  id: number
  name: string
  slug: string
  primary_color: string
  secondary_color: string
}
type WorkHit = {
  job_id: number
  kind: string
  title: string
  topic: string
  brand_name: string
  region_code: string
  editorial_status: string
  preview_url: string | null
}
type Results = {
  query: string
  topics: TopicHit[]
  brands: BrandHit[]
  work: WorkHit[]
  total: number
}

const EMPTY: Results = { query: '', topics: [], brands: [], work: [], total: 0 }

export function GlobalSearch() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Results>(EMPTY)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  /** Which result the keyboard is on; -1 is the field itself. */
  const [cursor, setCursor] = useState(-1)
  const box = useRef<HTMLDivElement>(null)
  const field = useRef<HTMLInputElement>(null)
  const listId = useId()
  const ticket = useRef(0)

  // Cmd/Ctrl-K from anywhere. The shortcut is the reason this is worth
  // having in the top bar rather than on a page of its own.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        field.current?.focus()
        field.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Clicking anywhere else closes it. Pointerdown rather than click, so the
  // panel is gone before whatever was clicked begins to happen.
  useEffect(() => {
    if (!open) return
    function onDown(event: PointerEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false)
    }
    window.addEventListener('pointerdown', onDown)
    return () => window.removeEventListener('pointerdown', onDown)
  }, [open])

  useEffect(() => {
    const text = q.trim()
    if (text.length < 2) {
      setResults(EMPTY)
      setBusy(false)
      return
    }

    setBusy(true)
    const mine = ++ticket.current
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const response = await fetch(`${API}/search?q=${encodeURIComponent(text)}`, {
            cache: 'no-store',
          })
          if (!response.ok) throw new Error(String(response.status))
          const body = (await response.json()) as Results
          // Guards an older answer landing after a newer one, which on a
          // box typed into quickly is most of them.
          if (mine === ticket.current) {
            setResults(body)
            setCursor(-1)
          }
        } catch {
          if (mine === ticket.current) setResults(EMPTY)
        } finally {
          if (mine === ticket.current) setBusy(false)
        }
      })()
    }, DEBOUNCE_MS)

    return () => clearTimeout(timer)
  }, [q])

  /** Everything on screen, flattened, so the arrow keys walk one list. */
  const flat: Array<{ key: string; href: string }> = [
    ...results.topics.map((t) => ({
      key: `t${t.trend_id}`,
      href: `/board?region=${t.region_code}&topic=${t.trend_id}`,
    })),
    ...results.brands.map((b) => ({ key: `b${b.id}`, href: `/brands/${b.id}` })),
    ...results.work.map((w) => ({
      key: `w${w.job_id}`,
      href: `/board?region=${w.region_code}&topic=${w.job_id}`,
    })),
  ]

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      setOpen(false)
      field.current?.blur()
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (flat.length === 0) return
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setCursor((current) => {
        const next = current + step
        if (next < 0) return -1
        return Math.min(next, flat.length - 1)
      })
      return
    }
    if (event.key === 'Enter' && cursor >= 0) {
      const target = flat[cursor]
      if (target) {
        event.preventDefault()
        window.location.href = target.href
      }
    }
  }

  const showPanel = open && q.trim().length >= 2

  return (
    <div ref={box} className="relative w-full max-w-md">
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-faint"
        strokeWidth={2}
      />
      <input
        ref={field}
        type="search"
        value={q}
        role="combobox"
        aria-expanded={showPanel}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label="Search topics, brands and posts"
        placeholder="Search topics, brands, posts"
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className={cx(
          'h-9 w-full rounded-sm border border-border bg-page pr-14 pl-8 text-sm text-ink',
          'placeholder:text-faint',
          'transition-[border-color] duration-150 hover:border-border-hover',
          // Safari draws its own clear button on type=search and it lands
          // on top of the shortcut hint.
          '[&::-webkit-search-cancel-button]:appearance-none',
        )}
      />
      <kbd
        aria-hidden="true"
        className="num pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 rounded-sm border border-border px-1.5 py-0.5 text-[11px] text-faint"
      >
        ⌘K
      </kbd>

      {showPanel ? (
        <div
          id={listId}
          role="listbox"
          aria-label="Search results"
          className="absolute top-full right-0 left-0 z-50 mt-1.5 max-h-[70vh] overflow-y-auto rounded-md border border-border bg-overlay shadow-overlay"
        >
          {busy && results.total === 0 ? (
            <p className="px-3 py-3 text-sm text-slate">Searching…</p>
          ) : results.total === 0 ? (
            <p className="px-3 py-3 text-sm text-slate">
              Nothing matching <span className="text-ink">{q.trim()}</span>.
            </p>
          ) : (
            <>
              <Group label="Topics" count={results.topics.length}>
                {results.topics.map((hit, i) => (
                  <Row
                    key={hit.trend_id}
                    href={`/board?region=${hit.region_code}&topic=${hit.trend_id}`}
                    active={cursor === i}
                    onPick={() => setOpen(false)}
                  >
                    <span className="num w-7 shrink-0 text-xs text-faint">#{hit.rank}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-ink">{hit.topic}</span>
                      <span className="block truncate text-xs text-faint">
                        {hit.region_name}
                        {hit.also_on > 0 ? ` and ${hit.also_on} other boards` : ''}
                      </span>
                    </span>
                  </Row>
                ))}
              </Group>

              <Group label="Brands" count={results.brands.length}>
                {results.brands.map((hit, i) => (
                  <Row
                    key={hit.id}
                    href={`/brands/${hit.id}`}
                    active={cursor === results.topics.length + i}
                    onPick={() => setOpen(false)}
                  >
                    <span aria-hidden="true" className="flex shrink-0 gap-0.5">
                      <span
                        className="block size-4 rounded-[3px] border border-border"
                        style={{ backgroundColor: hit.primary_color }}
                      />
                      <span
                        className="block size-4 rounded-[3px] border border-border"
                        style={{ backgroundColor: hit.secondary_color }}
                      />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-ink">{hit.name}</span>
                  </Row>
                ))}
              </Group>

              <Group label="Posts and reels" count={results.work.length}>
                {results.work.map((hit, i) => (
                  <Row
                    key={hit.job_id}
                    href={`/library?q=${encodeURIComponent(hit.topic)}`}
                    active={cursor === results.topics.length + results.brands.length + i}
                    onPick={() => setOpen(false)}
                  >
                    {hit.preview_url ? (
                      /* A MinIO URL on a published port. */
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={hit.preview_url}
                        alt=""
                        className="size-8 shrink-0 rounded-[3px] border border-border object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <span className="size-8 shrink-0 rounded-[3px] border border-border bg-card" />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-ink">{hit.title}</span>
                      <span className="block truncate text-xs text-faint">{hit.brand_name}</span>
                    </span>
                    <Chip tone="neutral" className="shrink-0 capitalize">
                      {hit.editorial_status}
                    </Chip>
                  </Row>
                ))}
              </Group>
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}

function Group({
  label,
  count,
  children,
}: {
  label: string
  count: number
  children: React.ReactNode
}) {
  if (count === 0) return null
  return (
    <section className="border-b border-border last:border-b-0">
      <h3 className="px-3 pt-2.5 pb-1 text-xs font-medium text-faint">{label}</h3>
      <ul className="pb-1.5">{children}</ul>
    </section>
  )
}

function Row({
  href,
  active,
  onPick,
  children,
}: {
  href: string
  active: boolean
  onPick: () => void
  children: React.ReactNode
}) {
  return (
    <li>
      <Link
        href={href}
        onClick={onPick}
        role="option"
        aria-selected={active}
        className={cx(
          'flex items-center gap-2.5 px-3 py-1.5',
          'transition-[background-color] duration-150',
          active ? 'bg-row-active' : 'hover:bg-row-hover',
        )}
      >
        {children}
      </Link>
    </li>
  )
}
