'use client'

import type { Brand } from '@trendforge/types'
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { cx } from '@/components/ui'

/**
 * "Generate for the top N", above the ladder.
 *
 * The Desk generates one post at a time, which is right when a person is
 * reading a topic and deciding. It is wrong at the start of a week, when
 * the answer is "the top ten, for this brand, in English".
 *
 * The button names the real number before the click. The API's /plan says
 * how many it would actually queue once today's budget and the already-done
 * topics are taken off, and that number is what the button says — "Generate
 * 3 posts" rather than "Generate for top 10" followed by a surprise.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

/** Offered sizes. Ten is a week of daily posts. */
const SIZES = [3, 5, 10] as const

type Plan = {
  available: number
  remaining_today: number | null
  would_queue: number
  message: string
}

type Result = { queued: number[]; message: string }

export function BatchGenerate({
  brands,
  region,
  disabled,
}: {
  brands: Brand[]
  region: string
  /** No topics on this board, so there is nothing to generate from. */
  disabled: boolean
}) {
  const [open, setOpen] = useState(false)
  const [brandId, setBrandId] = useState(() => brands[0]?.id ?? 0)
  const [language, setLanguage] = useState(() => brands[0]?.languages?.[0] ?? 'english')
  const [n, setN] = useState<number>(5)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const request = useCallback(
    (path: string) =>
      fetch(`${API}/content/batch${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ brand_id: brandId, region, n, language }),
      }),
    [brandId, region, n, language],
  )

  // Re-planned on every change, because every one of them moves the number.
  useEffect(() => {
    if (!open || !brandId) return
    let cancelled = false
    setPlan(null)
    setError(null)

    void (async () => {
      try {
        const response = await request('/plan')
        if (!response.ok) throw new Error(`The API returned ${response.status}.`)
        const body = (await response.json()) as Plan
        if (!cancelled) setPlan(body)
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'Could not reach the API.')
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [open, brandId, request])

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const response = await request('')
      if (!response.ok) {
        const detail = (await response.json().catch(() => null)) as { detail?: string } | null
        throw new Error(detail?.detail ?? `The API returned ${response.status}.`)
      }
      setResult((await response.json()) as Result)
      setPlan(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start the batch.')
    } finally {
      setBusy(false)
    }
  }

  if (brands.length === 0) {
    return (
      <p className="border-b border-border px-4 py-3 text-xs text-slate">
        <Link href="/brands/new" className="text-ink underline underline-offset-2">
          Make a brand
        </Link>{' '}
        to generate posts from this board.
      </p>
    )
  }

  if (!open) {
    return (
      <div className="border-b border-border px-4 py-2.5">
        <button
          type="button"
          onClick={() => setOpen(true)}
          disabled={disabled}
          className="text-xs text-slate underline underline-offset-2 hover:text-ink disabled:no-underline disabled:opacity-50"
        >
          Generate for the top topics
        </button>
      </div>
    )
  }

  return (
    <div className="border-b border-border px-4 py-3">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate">Brand</span>
          <select
            value={brandId}
            onChange={(e) => {
              const id = Number(e.target.value)
              setBrandId(id)
              const picked = brands.find((b) => b.id === id)
              setLanguage(picked?.languages?.[0] ?? 'english')
            }}
            className={INPUT}
          >
            {brands.map((brand) => (
              <option key={brand.id} value={brand.id}>
                {brand.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate">Language</span>
          <select value={language} onChange={(e) => setLanguage(e.target.value)} className={INPUT}>
            {(brands.find((b) => b.id === brandId)?.languages ?? ['english']).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate">How many</span>
          <div className="flex gap-px" role="group" aria-label="How many">
            {SIZES.map((size) => (
              <button
                key={size}
                type="button"
                aria-pressed={n === size}
                onClick={() => setN(size)}
                className={cx(
                  'num border px-2.5 py-1.5 text-sm',
                  n === size
                    ? 'border-ink bg-ink text-page'
                    : 'border-border text-slate hover:text-ink',
                )}
              >
                {size}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          onClick={run}
          disabled={busy || !plan || plan.would_queue === 0}
          className="border border-ink bg-ink px-3.5 py-1.5 text-sm text-page disabled:opacity-40"
        >
          {busy
            ? 'Queueing…'
            : plan
              ? // The number the API will actually queue, not the one the
                // chips show — those differ exactly when it matters.
                `Generate ${plan.would_queue} ${plan.would_queue === 1 ? 'post' : 'posts'}`
              : 'Checking…'}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false)
            setResult(null)
          }}
          className="text-xs text-slate underline underline-offset-2 hover:text-ink"
        >
          Close
        </button>

        {plan && plan.would_queue < n ? (
          <span className="text-xs text-slate">{plan.message}</span>
        ) : null}
        {plan?.remaining_today !== null && plan?.remaining_today !== undefined ? (
          <span className="num text-xs text-slate">
            {plan.remaining_today} model calls left today
          </span>
        ) : null}
      </div>

      {result ? (
        <p className="mt-2.5 text-xs text-ink">
          {result.message}{' '}
          <Link href="/library" className="underline underline-offset-2">
            Watch them in the library
          </Link>
          .
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2.5 text-xs text-chilli">
          {error}
        </p>
      ) : null}
    </div>
  )
}

const INPUT = 'border border-border bg-card px-2 py-1.5 text-sm text-ink'
