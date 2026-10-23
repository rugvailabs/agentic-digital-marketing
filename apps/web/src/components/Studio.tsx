'use client'

import type { Brand, ContentJob, Trend } from '@trendforge/types'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Chip, Code, cx } from '@/components/primitives'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8020'

/** A job is terminal when it will not change again without a new request. */
const TERMINAL = new Set(['ready', 'failed'])
const POLL_MS = 2000
/** Generation runs through several Gemini models on a free tier; it is slow. */
const POLL_TIMEOUT_MS = 10 * 60 * 1000

const LANGUAGE_LABELS: Record<string, string> = {
  english: 'English',
  hinglish: 'Hinglish',
  hindi: 'हिन्दी',
  tamil: 'தமிழ்',
  telugu: 'తెలుగు',
  bengali: 'বাংলা',
  marathi: 'मराठी',
}

/** "square:bold-type" -> "Bold type · square". The raw variant truncates to
 *  "square:…" in a card footer, which tells the user nothing. */
function variantLabel(variant: string): string {
  const [size, template] = variant.split(':')
  if (!template) return variant
  const name = template.replace(/-/g, ' ')
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} · ${size}`
}

const STATUS_LABELS: Record<string, string> = {
  queued: 'Queued',
  writing: 'Writing the caption',
  rendering: 'Rendering images',
  ready: 'Ready',
  failed: 'Failed',
}

type Caption = {
  hook?: string
  caption?: string
  hashtags?: string[]
  alt_text?: string
  image_headline?: string
}

export function Studio({ trend, brands }: { trend: Trend; brands: Brand[] }) {
  const [brandId, setBrandId] = useState(brands[0]?.id ?? 0)
  const [language, setLanguage] = useState('english')
  const [job, setJob] = useState<ContentJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Switching topic must not leave the previous topic's post on screen, and
  // a topic that already has a post should show it rather than looking unused.
  useEffect(() => {
    let cancelled = false
    setJob(null)
    setError(null)
    setBusy(false)

    void (async () => {
      try {
        const response = await fetch(`${API}/content/jobs?trend_id=${trend.id}`, {
          cache: 'no-store',
        })
        if (!response.ok || cancelled) return
        const existing = (await response.json()) as ContentJob | null
        if (existing && !cancelled) {
          setJob(existing)
          // Match the controls to what is on screen; leaving them on the
          // defaults claims a Hindi post was generated in English.
          setLanguage(existing.language)
          setBrandId(existing.brand_id)
        }
      } catch {
        // No previous job is the normal case; silence is correct here.
      }
    })()

    return () => {
      cancelled = true
    }
  }, [trend.id])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  const poll = useCallback(async (id: number, deadline: number) => {
    try {
      const response = await fetch(`${API}/content/jobs/${id}`, { cache: 'no-store' })
      if (!response.ok) throw new Error(`job ${id} returned ${response.status}`)
      const next = (await response.json()) as ContentJob

      setJob(next)
      if (TERMINAL.has(next.status)) {
        setBusy(false)
        return
      }
      if (Date.now() > deadline) {
        setBusy(false)
        setError('Still running after 10 minutes. The job keeps going — reload to check.')
        return
      }
      timer.current = setTimeout(() => void poll(id, deadline), POLL_MS)
    } catch (cause) {
      setBusy(false)
      setError(cause instanceof Error ? cause.message : 'Could not reach the API.')
    }
  }, [])

  async function generate() {
    setBusy(true)
    setError(null)
    setJob(null)
    try {
      const response = await fetch(`${API}/content/jobs`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          trend_id: trend.id,
          brand_id: brandId,
          language,
          formats: ['square', 'portrait'],
        }),
      })
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail ?? `The API returned ${response.status}.`)
      }
      const created = (await response.json()) as ContentJob
      setJob(created)
      void poll(created.id, Date.now() + POLL_TIMEOUT_MS)
    } catch (cause) {
      setBusy(false)
      setError(cause instanceof Error ? cause.message : 'Could not start the job.')
    }
  }

  const brand = brands.find((b) => b.id === brandId)
  const caption = job?.assets.find((a) => a.kind === 'caption')
  const images = job?.assets.filter((a) => a.kind === 'image') ?? []
  const blocked = trend.safety_flag === 'skip'

  return (
    <div className="border-t border-rule pt-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate">
          Brand
          <select
            value={brandId}
            onChange={(e) => setBrandId(Number(e.target.value))}
            className="border border-rule bg-surface px-2 py-1 text-sm text-ink"
          >
            {brands.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-slate">
          Language
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="border border-rule bg-surface px-2 py-1 text-sm text-ink"
          >
            {(brand?.languages ?? ['english']).map((code) => (
              <option key={code} value={code}>
                {LANGUAGE_LABELS[code] ?? code}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={() => void generate()}
          disabled={busy || blocked || brands.length === 0}
          className="border border-ink px-3 py-1.5 text-sm text-ink transition-colors hover:bg-row-hover disabled:border-rule disabled:text-slate"
        >
          {busy ? 'Generating' : 'Generate post'}
        </button>

        {job ? (
          <span className="num text-xs text-slate">
            {STATUS_LABELS[job.status] ?? job.status}
          </span>
        ) : null}
      </div>

      {blocked ? (
        <p className="mt-3 text-sm text-slate">
          This topic is flagged as one we do not market against, so the studio is off for it.
        </p>
      ) : null}

      {error || job?.error ? (
        <div className="mt-4 border-t border-rule pt-3">
          <p className="text-sm text-ink">{job?.error ?? error}</p>
          <button
            type="button"
            onClick={() => void generate()}
            className="mt-2 border border-ink px-3 py-1 text-sm text-ink hover:bg-row-hover"
          >
            Try again
          </button>
        </div>
      ) : null}

      {caption ? (
        <CaptionEditor assetId={caption.id} initial={caption.meta_json as Caption} />
      ) : null}

      {images.length > 0 ? (
        <div className="mt-6 flex flex-col gap-2">
          <h3 className="text-xs font-medium text-slate">
            {images.length} images · {brand?.name}
          </h3>
          {/* The only cards on the page: a border here means "rendered asset". */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
            {images.map((asset) => (
              <figure key={asset.id} className="border border-rule bg-surface p-3">
                {asset.url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={asset.url}
                    alt={String((asset.meta_json as Caption).alt_text ?? '')}
                    className="w-full"
                    loading="lazy"
                  />
                ) : null}
                <figcaption className="mt-2 flex items-center justify-between gap-2">
                  <span className="truncate text-xs text-slate" title={asset.variant}>
                    {variantLabel(asset.variant)}
                  </span>
                  {asset.url ? (
                    <a
                      href={asset.url}
                      download
                      className="shrink-0 text-xs text-ink underline decoration-rule underline-offset-2 hover:decoration-ink"
                    >
                      Save PNG
                    </a>
                  ) : null}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      ) : null}

      {!job && !error ? (
        <p className="mt-3 text-sm text-slate">
          Pick a brand and language, then generate a caption and post images for this topic.
        </p>
      ) : null}
    </div>
  )
}

function CaptionEditor({ assetId, initial }: { assetId: number; initial: Caption }) {
  const [text, setText] = useState(initial.caption ?? '')
  const [state, setState] = useState<'clean' | 'saving' | 'saved' | 'error'>('clean')

  // A fresh generation reuses this component; take the new text.
  useEffect(() => {
    setText(initial.caption ?? '')
    setState('clean')
  }, [initial.caption])

  async function save() {
    setState('saving')
    try {
      const response = await fetch(`${API}/content/assets/${assetId}`, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ caption: text }),
      })
      setState(response.ok ? 'saved' : 'error')
    } catch {
      setState('error')
    }
  }

  const words = text.trim() ? text.trim().split(/\s+/).length : 0

  return (
    <div className="mt-5 flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs font-medium text-slate">Caption</h3>
        <span className="num text-xs text-slate">{words} words</span>
      </div>

      {initial.hook ? <p className="text-sm font-medium text-ink">{initial.hook}</p> : null}

      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setState('clean')
        }}
        rows={5}
        className="w-full border border-rule bg-surface p-3 text-sm leading-relaxed text-ink"
      />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void save()}
          disabled={state === 'saving'}
          className="border border-ink px-3 py-1 text-sm text-ink hover:bg-row-hover disabled:border-rule disabled:text-slate"
        >
          {state === 'saving' ? 'Saving' : 'Save caption'}
        </button>
        <span
          className={cx('text-xs', state === 'error' ? 'text-chilli' : 'text-slate')}
        >
          {state === 'saved' ? 'Saved' : state === 'error' ? 'Could not save' : ''}
        </span>
      </div>

      {initial.hashtags?.length ? (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {initial.hashtags.map((tag) => (
            <Chip key={tag}>{tag}</Chip>
          ))}
        </div>
      ) : null}

      {initial.alt_text ? (
        <p className="mt-2 text-xs text-slate">
          <Code>alt</Code> {initial.alt_text}
        </p>
      ) : null}
    </div>
  )
}
