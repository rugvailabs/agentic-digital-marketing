'use client'

import type { Brand, ContentAsset, Trend } from '@trendforge/types'
import { useEffect, useState } from 'react'

import { Reel } from '@/components/Reel'
import { Chip, Code, SectionLabel, cx } from '@/components/primitives'
import { statusLabel, useJob } from '@/lib/jobs'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

const LANGUAGE_LABELS: Record<string, string> = {
  english: 'English',
  hinglish: 'Hinglish',
  hindi: 'हिन्दी',
  tamil: 'தமிழ்',
  telugu: 'తెలుగు',
  bengali: 'বাংলা',
  marathi: 'मराठी',
}

/** Full template names. The renderer sends one in `meta.label`; this is the
 *  fallback for assets rendered before it did. "square:…" told nobody
 *  anything. */
const TEMPLATE_LABELS: Record<string, string> = {
  poster: 'Poster',
  split: 'Split panel',
  wire: 'Wire',
  'bold-type': 'Bold type',
  'split-panel': 'Split panel',
  'flat-colour': 'Flat colour',
}

function templateLabel(asset: { variant: string; meta_json: Record<string, unknown> }): string {
  const label = asset.meta_json?.label
  if (typeof label === 'string' && label) return label
  const template = asset.variant.split(':')[1] ?? asset.variant
  return TEMPLATE_LABELS[template] ?? template.replace(/-/g, ' ')
}

function dimensions(asset: { meta_json: Record<string, unknown> }): string {
  const { width, height } = asset.meta_json as { width?: number; height?: number }
  return width && height ? `${width}×${height}` : ''
}

type Caption = {
  hook?: string
  caption?: string
  hashtags?: string[]
  alt_text?: string
  image_headline?: string
}

/**
 * The content studio.
 *
 * One row of controls — brand, language — then two things that can be made
 * from them: a post and a reel. They are separate jobs on separate pipelines
 * with their own statuses and their own failures, but a marketer picks the
 * brand and the language once, not twice.
 */
export function Studio({ trend, brands }: { trend: Trend; brands: Brand[] }) {
  const [brandId, setBrandId] = useState(brands[0]?.id ?? 0)
  const [language, setLanguage] = useState('english')

  const post = useJob(trend.id, 'post')
  const reel = useJob(trend.id, 'reel')

  // Match the controls to whatever is already on screen; leaving them on the
  // defaults claims a Hindi post was generated in English.
  const existing = post.job ?? reel.job
  useEffect(() => {
    if (!existing) return
    setLanguage(existing.language)
    setBrandId(existing.brand_id)
  }, [existing])

  const brand = brands.find((b) => b.id === brandId)
  const caption = post.job?.assets.find((a) => a.kind === 'caption')
  const images = post.job?.assets.filter((a) => a.kind === 'image') ?? []
  const blocked = trend.safety_flag === 'skip'
  const noBrands = brands.length === 0

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
          onClick={() => post.start({ brandId, language, formats: ['square', 'portrait'] })}
          disabled={post.busy || blocked || noBrands}
          className="border border-ink px-3 py-1.5 text-sm text-ink transition-colors hover:bg-row-hover disabled:border-rule disabled:text-slate"
        >
          {post.busy ? 'Generating' : 'Generate post'}
        </button>

        {post.job ? (
          <span className="num text-xs text-slate">{statusLabel('post', post.job.status)}</span>
        ) : null}
      </div>

      {blocked ? (
        <p className="mt-3 text-sm text-slate">
          This topic is flagged as one we do not market against, so the studio is off for it.
        </p>
      ) : null}

      {post.error || post.job?.error ? (
        <div className="mt-4 border-t border-rule pt-3">
          <p className="text-sm text-ink">{post.job?.error ?? post.error}</p>
          <button
            type="button"
            onClick={() => post.start({ brandId, language, formats: ['square', 'portrait'] })}
            className="mt-2 border border-ink px-3 py-1 text-sm text-ink hover:bg-row-hover"
          >
            Try again
          </button>
        </div>
      ) : null}

      {caption ? (
        <CaptionEditor assetId={caption.id} initial={caption.meta_json as Caption} />
      ) : null}

      {images.length > 0 ? <Images images={images} brandName={brand?.name} /> : null}

      {!post.job && !post.error && !blocked ? (
        <p className="mt-3 text-sm text-slate">
          Pick a brand and language, then generate a caption and post images for this topic.
        </p>
      ) : null}

      <Reel
        job={reel.job}
        busy={reel.busy}
        error={reel.error}
        onRender={() => reel.start({ brandId, language, formats: ['reel'] })}
        blocked={blocked}
        disabled={noBrands}
      />
    </div>
  )
}

function Images({ images, brandName }: { images: ContentAsset[]; brandName?: string }) {
  return (
    <div className="mt-6 flex flex-col gap-2">
      <SectionLabel>
        {images.length} images{brandName ? ` · ${brandName}` : ''}
      </SectionLabel>
      {/* A border here means "a rendered asset lives here". */}
      {/* items-start so a portrait card keeps its height instead of
          stretching its square neighbours to match. */}
      <div className="grid grid-cols-2 items-start gap-4 lg:grid-cols-3">
        {images.map((asset) => (
          <figure key={asset.id} className="border border-rule bg-surface p-3">
            {asset.url ? (
              // Intrinsic size on the element, so a 1080x1350 post holds its
              // 4:5 shape instead of being squared off by the grid.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={asset.url}
                alt={String((asset.meta_json as Caption).alt_text ?? '')}
                width={Number((asset.meta_json as { width?: number }).width) || 1080}
                height={Number((asset.meta_json as { height?: number }).height) || 1080}
                className="h-auto w-full"
                loading="lazy"
              />
            ) : null}
            {/*
              Two lines, so the template name is never abbreviated: at three
              cards per row there is not enough width for a name, its
              dimensions and a link side by side.
            */}
            <figcaption className="mt-2 flex flex-col gap-0.5">
              <span className="text-xs text-ink">{templateLabel(asset)}</span>
              <span className="flex items-baseline justify-between gap-2">
                <span className="num text-xs text-slate">{dimensions(asset)}</span>
                {asset.url ? (
                  <a
                    href={asset.url}
                    download
                    className="shrink-0 text-xs text-ink underline decoration-rule underline-offset-2 hover:decoration-ink"
                  >
                    Save PNG
                  </a>
                ) : null}
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
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
        <SectionLabel>Caption</SectionLabel>
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
        <span className={cx('text-xs', state === 'error' ? 'text-chilli' : 'text-slate')}>
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
