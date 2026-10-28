'use client'

import type { Brand, ContentAsset, Trend } from '@trendforge/types'
import { useEffect, useState } from 'react'

import Link from 'next/link'

import { AssetCard } from '@/components/desk/AssetCard'
import { Reel } from '@/components/Reel'
import {
  Button,
  Chip,
  Code,
  Empty,
  Field,
  SectionLabel,
  Select,
  Textarea,
  cx,
} from '@/components/ui'
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
 * The content studio, for one kind of thing at a time.
 *
 * It used to make both from one screen — brand, language, then a post and
 * a reel stacked below each other. The Desk's tabs split them, and `kind`
 * is how: the brand and language row is identical for both and is written
 * once here, but a post and a reel are separate jobs on separate pipelines
 * with their own statuses and their own failures, and now with their own
 * tab.
 */
export function Studio({
  trend,
  brands,
  kind,
}: {
  trend: Trend
  brands: Brand[]
  kind: 'post' | 'reel'
}) {
  const [brandId, setBrandId] = useState(brands[0]?.id ?? 0)
  const [language, setLanguage] = useState('english')

  const job = useJob(trend.id, kind)

  // Match the controls to whatever is already on screen; leaving them on
  // the defaults claims a Hindi post was generated in English.
  useEffect(() => {
    if (!job.job) return
    setLanguage(job.job.language)
    setBrandId(job.job.brand_id)
  }, [job.job])

  const brand = brands.find((b) => b.id === brandId)
  const caption = job.job?.assets.find((a) => a.kind === 'caption')
  const images = job.job?.assets.filter((a) => a.kind === 'image') ?? []
  const blocked = trend.safety_flag === 'skip'
  const formats = kind === 'reel' ? ['reel'] : ['square', 'portrait']

  if (brands.length === 0) {
    return (
      <Empty
        title="There is no brand to generate for."
        hint={
          <>
            <Link href="/brands/new" className="text-ink underline underline-offset-2">
              Make one
            </Link>{' '}
            and it will appear here.
          </>
        }
      />
    )
  }

  if (blocked) {
    return (
      <Empty
        title="This topic is flagged as one we do not market against."
        hint="The studio is off for it. The curator decides this, not the writer."
      />
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Brand" className="w-48">
          <Select value={brandId} onChange={(e) => setBrandId(Number(e.target.value))}>
            {brands.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Language" className="w-40">
          <Select value={language} onChange={(e) => setLanguage(e.target.value)}>
            {(brand?.languages ?? ['english']).map((code) => (
              <option key={code} value={code}>
                {LANGUAGE_LABELS[code] ?? code}
              </option>
            ))}
          </Select>
        </Field>

        <Button
          variant="primary"
          onClick={() => job.start({ brandId, language, formats })}
          disabled={job.busy}
        >
          {job.busy
            ? kind === 'reel'
              ? 'Rendering'
              : 'Generating'
            : kind === 'reel'
              ? 'Render reel'
              : 'Generate post'}
        </Button>

        {job.job ? (
          <span className="num pb-2 text-xs text-slate">{statusLabel(kind, job.job.status)}</span>
        ) : null}
      </div>

      {job.error || job.job?.error ? (
        <div className="rounded-md border border-chilli/40 p-3">
          <p className="text-sm text-ink">{job.job?.error ?? job.error}</p>
          <Button
            size="sm"
            className="mt-2"
            onClick={() => job.start({ brandId, language, formats })}
          >
            Try again
          </Button>
        </div>
      ) : null}

      {kind === 'post' ? (
        <>
          {caption ? (
            <CaptionEditor assetId={caption.id} initial={caption.meta_json as Caption} />
          ) : null}
          {images.length > 0 ? (
            <Images images={images} brandName={brand?.name} jobId={job.job?.id} />
          ) : null}
          {!job.job && !job.error ? (
            <Empty
              title="Nothing generated for this topic yet."
              hint="Pick a brand and a language, then generate a caption and three post images."
            />
          ) : null}
        </>
      ) : (
        <Reel job={job.job} busy={job.busy} />
      )}
    </div>
  )
}

function Images({
  images,
  brandName,
  jobId,
}: {
  images: ContentAsset[]
  brandName?: string
  jobId?: number
}) {
  return (
    <div className="flex flex-col gap-2">
      <SectionLabel>
        {images.length} images{brandName ? ` for ${brandName}` : ''}
      </SectionLabel>
      {/* items-start so a portrait card keeps its height instead of
          stretching its square neighbours to match. */}
      <div className="grid grid-cols-2 items-start gap-4 lg:grid-cols-3">
        {images.map((asset) => (
          <AssetCard
            key={asset.id}
            url={asset.url}
            jobId={jobId}
            title={templateLabel(asset)}
            subtitle={dimensions(asset)}
          >
            {asset.url ? (
              // Intrinsic size on the element, so a 1080x1350 post holds
              // its 4:5 shape instead of being squared off by the grid.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={asset.url}
                alt={String((asset.meta_json as Caption).alt_text ?? '')}
                width={Number((asset.meta_json as { width?: number }).width) || 1080}
                height={Number((asset.meta_json as { height?: number }).height) || 1080}
                className="block h-auto w-full"
                loading="lazy"
              />
            ) : (
              <span className="block aspect-square w-full bg-page" />
            )}
          </AssetCard>
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
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <SectionLabel>Caption</SectionLabel>
        <span className="num text-xs text-slate">{words} words</span>
      </div>

      {initial.hook ? <p className="text-sm font-medium text-ink">{initial.hook}</p> : null}

      <Textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setState('clean')
        }}
        rows={5}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => void save()} disabled={state === 'saving'}>
          {state === 'saving' ? 'Saving' : 'Save caption'}
        </Button>
        <span className={cx('text-xs', state === 'error' ? 'text-chilli' : 'text-neem')}>
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
