'use client'

import type { Brand, Language, Region } from '@trendforge/types'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Button, Field, Input, SectionLabel, Select, Textarea } from '@/components/house'
import {
  TEMPLATES,
  TEMPLATE_LABELS,
  TEMPLATE_NOTES,
  TemplatePreview,
} from '@/components/TemplatePreview'
import {
  BrandError,
  type BrandForm,
  createBrand,
  deleteBrand,
  formOf,
  linesOf,
  removeLogo,
  textOf,
  updateBrand,
  uploadLogo,
} from '@/lib/brand'

/**
 * Create or edit one brand, with the three post templates redrawing beside
 * the form.
 *
 * The preview is the point. A voice prompt is abstract and a hex code is
 * four characters; what a team actually wants to know is whether their red
 * on their logo reads at post size, and the only honest way to answer that
 * is to show it while they type.
 */

const LANGUAGES: Language[] = [
  'english',
  'hinglish',
  'hindi',
  'tamil',
  'telugu',
  'bengali',
  'marathi',
]

/** Sentence case, as CLAUDE.md asks. The API stores the lower-case value. */
const LANGUAGE_LABELS: Record<Language, string> = {
  english: 'English',
  hinglish: 'Hinglish',
  hindi: 'Hindi',
  tamil: 'Tamil',
  telugu: 'Telugu',
  bengali: 'Bengali',
  marathi: 'Marathi',
}

const FACES = [
  { value: 'display', label: 'Bricolage Grotesque', note: 'The board’s display face' },
  { value: 'ui', label: 'Schibsted Grotesk', note: 'Quieter, better for long headlines' },
]

export function BrandEditor({ brand, regions }: { brand: Brand | null; regions: Region[] }) {
  const router = useRouter()
  const [form, setForm] = useState<BrandForm>(() => formOf(brand))
  const [saved, setSaved] = useState<Brand | null>(brand)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  // What the preview shows: the uploaded file before it is saved, otherwise
  // whatever the API has. A blob URL, so the preview answers while the
  // upload is still a plan.
  const [pending, setPending] = useState<{ file: File; url: string } | null>(null)
  const logoUrl = pending?.url ?? saved?.logo_url ?? null

  // Blob URLs are not collected until they are revoked, and this component
  // makes a new one every time the picker is used.
  useEffect(() => () => void (pending && URL.revokeObjectURL(pending.url)), [pending])

  const set = <K extends keyof BrandForm>(key: K, value: BrandForm[K]) => {
    setForm((previous) => ({ ...previous, [key]: value }))
    setNote(null)
  }

  const previewBrand = useMemo(
    () => ({
      name: form.name,
      logoUrl,
      primaryColor: form.primary_color,
      secondaryColor: form.secondary_color,
      fontChoice: form.font_choice,
    }),
    [form.name, form.primary_color, form.secondary_color, form.font_choice, logoUrl],
  )

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setNote(null)

    try {
      let result = saved ? await updateBrand(saved.id, form) : await createBrand(form)
      if (pending) {
        // After the brand exists, because the upload is addressed to its id.
        // A new brand's first save is therefore two requests, which is worth
        // it to keep the logo endpoint from having to create brands too.
        result = await uploadLogo(result.id, pending.file)
        URL.revokeObjectURL(pending.url)
        setPending(null)
      }

      setSaved(result)
      setForm(formOf(result))
      setNote('Saved.')
      // So the board's brand picker and the list behind this page both see it.
      router.refresh()
      if (!brand) router.replace(`/brands/${result.id}`)
    } catch (cause) {
      setError(cause instanceof BrandError ? cause.message : 'Could not save this brand.')
    } finally {
      setBusy(false)
    }
  }

  async function discardLogo() {
    if (pending) {
      URL.revokeObjectURL(pending.url)
      setPending(null)
      return
    }
    if (!saved?.logo_url) return

    setBusy(true)
    try {
      setSaved(await removeLogo(saved.id))
      setNote('Logo removed.')
    } catch (cause) {
      setError(cause instanceof BrandError ? cause.message : 'Could not remove the logo.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={save} className="desk:grid-cols-[minmax(0,1fr)_minmax(0,420px)] grid gap-10">
      <div className="min-w-0">
        <Field label="Name" hint="Shown on every post that has no logo." className={SECTION}>
          <Input
            required
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Madras Filter Coffee"
          />
        </Field>

        <Field
          className={SECTION}
          label="URL name"
          hint={
            saved
              ? 'Changing this changes the brand’s address.'
              : 'Left blank, it is made from the name.'
          }
        >
          <Input
            value={form.slug}
            onChange={(e) => set('slug', e.target.value)}
            placeholder={suggestSlug(form.name)}
            className="font-mono"
          />
        </Field>

        <Field
          className={SECTION}
          label="Voice"
          hint="Goes to the writer with every caption. Say how it sounds."
        >
          <Textarea
            rows={3}
            value={form.voice_prompt}
            onChange={(e) => set('voice_prompt', e.target.value)}
            placeholder="Warm, specific, a little dry. Short sentences. No exclamation marks."
          />
        </Field>

        <fieldset className="mt-8 border-t border-border pt-5">
          <SectionLabel>Colour</SectionLabel>
          <div className="mt-3 flex flex-wrap gap-8">
            <Colour
              label="Primary"
              hint="The Poster ground"
              value={form.primary_color}
              onChange={(value) => set('primary_color', value)}
            />
            <Colour
              label="Secondary"
              hint="The Split block and the Poster rule"
              value={form.secondary_color}
              onChange={(value) => set('secondary_color', value)}
            />
          </div>
        </fieldset>

        <Logo
          url={logoUrl}
          unsaved={pending !== null}
          onPick={(file) => {
            if (pending) URL.revokeObjectURL(pending.url)
            setPending({ file, url: URL.createObjectURL(file) })
            setNote(null)
          }}
          onClear={discardLogo}
        />

        <fieldset className="mt-8 border-t border-border pt-5">
          <SectionLabel>Headline face</SectionLabel>
          <div className="mt-3 flex flex-col gap-2">
            {FACES.map((option) => (
              <label key={option.value} className="flex items-baseline gap-2.5 text-sm">
                <input
                  type="radio"
                  name="font_choice"
                  checked={form.font_choice === option.value}
                  onChange={() => set('font_choice', option.value)}
                  className="accent-chilli"
                />
                <span className="text-ink">{option.label}</span>
                <span className="text-xs text-slate">{option.note}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="mt-8 border-t border-border pt-5">
          <SectionLabel>Languages</SectionLabel>
          <p className="mt-1 text-xs text-slate">
            Which languages this brand publishes in. Captions are written in one at a time.
          </p>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
            {LANGUAGES.map((language) => (
              <label key={language} className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={form.languages.includes(language)}
                  onChange={(e) =>
                    set(
                      'languages',
                      e.target.checked
                        ? [...form.languages, language]
                        : form.languages.filter((l) => l !== language),
                    )
                  }
                  className="accent-chilli"
                />
                {LANGUAGE_LABELS[language]}
              </label>
            ))}
          </div>
        </fieldset>

        <Field label="Default region" hint="The board this brand opens on." className={SECTION}>
          <Select
            value={form.default_region_code ?? ''}
            onChange={(e) => set('default_region_code', e.target.value || null)}
          >
            <option value="">India</option>
            {regions
              .filter((region) => region.code !== 'IN')
              .map((region) => (
                <option key={region.code} value={region.code}>
                  {region.name}
                </option>
              ))}
          </Select>
        </Field>

        <Field
          className={SECTION}
          label="What you sell"
          hint="One per line. The writer uses these to tie a trend to something you actually offer."
        >
          <Textarea
            rows={4}
            value={textOf(form.products)}
            onChange={(e) => set('products', linesOf(e.target.value))}
            placeholder={'Filter coffee subscriptions\nCold brew cans'}
          />
        </Field>

        <Field label="Never mention" hint="One per line. Competitors, prices, anything off limits.">
          <Textarea
            rows={3}
            value={textOf(form.do_not_mention)}
            onChange={(e) => set('do_not_mention', linesOf(e.target.value))}
            placeholder={'Competitor Ltd\npricing'}
          />
        </Field>

        <div className="mt-8 flex flex-wrap items-center gap-4 border-t border-border pt-5">
          <Button type="submit" variant="primary" disabled={busy || !form.name.trim()}>
            {busy ? 'Saving…' : saved ? 'Save brand' : 'Create brand'}
          </Button>
          {saved ? <DeleteBrand brand={saved} /> : null}
          {note ? <span className="text-sm text-neem">{note}</span> : null}
          {error ? (
            <span role="alert" className="text-sm text-chilli">
              {error}
            </span>
          ) : null}
        </div>
      </div>

      {/*
       * Sticky, so the preview stays beside whichever field is being
       * edited. The form is long enough that the colour pickers and the
       * Poster template were a screen apart, which is the one pairing the
       * preview exists for.
       *
       * `h-fit` is what makes it work in a grid: a grid item is stretched
       * to the row's height by default, and a sticky element inside a
       * full-height box has nothing to stick within.
       */}
      <aside className="desk:sticky desk:top-[calc(var(--spacing-topbar)+1.25rem)] min-w-0 self-start">
        <SectionLabel>Preview</SectionLabel>
        <p className="mt-1 text-xs text-faint">
          Every post is rendered in all three. Sample copy, your brand.
        </p>
        <div className="desk:max-h-[calc(100dvh-var(--spacing-topbar)-5rem)] mt-4 flex flex-col gap-5 overflow-y-auto pr-1">
          {TEMPLATES.map((template) => (
            <div key={template}>
              <TemplatePreview template={template} brand={previewBrand} />
              <p className="mt-2 flex items-baseline justify-between text-xs">
                <span className="text-ink">{TEMPLATE_LABELS[template]}</span>
                <span className="text-faint">{TEMPLATE_NOTES[template]}</span>
              </p>
            </div>
          ))}
        </div>
      </aside>
    </form>
  )
}

function DeleteBrand({ brand }: { brand: Brand }) {
  const router = useRouter()
  const [confirming, setConfirming] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function go(force: boolean) {
    setBusy(true)
    try {
      await deleteBrand(brand.id, force)
      router.push('/brands')
      router.refresh()
    } catch (cause) {
      // The API refuses the first time and says how much work would go with
      // it. That count is the confirmation, so it is shown rather than a
      // generic "are you sure".
      if (cause instanceof BrandError && cause.status === 409) setConfirming(cause.message)
      else setConfirming(cause instanceof BrandError ? cause.message : 'Could not delete.')
    } finally {
      setBusy(false)
    }
  }

  if (confirming) {
    return (
      <span className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-ink">{confirming}</span>
        <Button variant="danger" onClick={() => void go(true)} disabled={busy}>
          Delete anyway
        </Button>
        <Button variant="quiet" onClick={() => setConfirming(null)}>
          Keep it
        </Button>
      </span>
    )
  }

  return (
    <Button variant="quiet" onClick={() => void go(false)} disabled={busy}>
      Delete brand
    </Button>
  )
}

function Logo({
  url,
  unsaved,
  onPick,
  onClear,
}: {
  url: string | null
  unsaved: boolean
  onPick: (file: File) => void
  onClear: () => void
}) {
  const input = useRef<HTMLInputElement>(null)

  return (
    <fieldset className="mt-8 border-t border-border pt-5">
      <SectionLabel>Logo</SectionLabel>
      <p className="mt-1 text-xs text-slate">
        PNG, JPEG or WebP, under 2 MB. Not SVG — the image renderer cannot draw one. Transparent
        padding is trimmed, and the logo replaces the brand name in the footer.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-4">
        <div className="flex h-16 w-32 items-center justify-center border border-border bg-card px-2">
          {url ? (
            // eslint-disable-next-line @next/next/no-img-element -- blob: URL
            <img src={url} alt="" className="max-h-12 max-w-full object-contain" />
          ) : (
            <span className="text-xs text-slate">No logo</span>
          )}
        </div>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onPick(file)
            // Cleared so picking the same file twice fires change again.
            e.target.value = ''
          }}
          className="hidden"
        />
        <Button onClick={() => input.current?.click()}>
          {url ? 'Replace logo' : 'Upload logo'}
        </Button>
        {url ? (
          <Button variant="quiet" onClick={onClear}>
            Remove
          </Button>
        ) : null}
        {unsaved ? <span className="text-xs text-slate">Uploads when you save.</span> : null}
      </div>
    </fieldset>
  )
}

function Colour({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-slate">{label}</span>
      <span className="flex items-center gap-2">
        <input
          type="color"
          value={/^#[0-9a-fA-F]{6}$/.test(value) ? value : '#000000'}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-8 w-10 cursor-pointer border border-border bg-card p-0.5"
          aria-label={`${label} colour`}
        />
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          spellCheck={false}
          className="num w-28 font-mono"
          aria-label={`${label} hex`}
        />
      </span>
      <span className="text-xs text-slate">{hint}</span>
    </label>
  )
}

/** Every field is a section of the form, separated by a rule. Spacing at
 *  the call site rather than inside Field, which is shared with forms that
 *  are not laid out this way. */
const SECTION = 'mt-8 border-t border-border pt-5'

/** Mirrors the API's slugify closely enough to be a placeholder, not a promise. */
function suggestSlug(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return slug || 'madras-filter-coffee'
}
