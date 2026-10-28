import type { Brand } from '@trendforge/types'

/**
 * Brand editing from the browser.
 *
 * The board is server-rendered, but a brand form is not: it writes, it
 * uploads a file, and the preview beside it has to redraw on every keystroke.
 * So these talk to the API directly, the same way `jobs.ts` does.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

/** What the API said went wrong, rather than "Request failed". */
export class BrandError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API}${path}`, { cache: 'no-store', ...init })
  } catch {
    throw new BrandError(`Could not reach the API at ${API}.`, 0)
  }

  if (!response.ok) {
    // FastAPI's `detail` is either a string we wrote or an array of
    // validation errors. The string is the useful one; the array is turned
    // into the field name and message a user can act on.
    const body = (await response.json().catch(() => null)) as {
      detail?: string | Array<{ loc?: unknown[]; msg?: string }>
    } | null
    throw new BrandError(
      detailOf(body?.detail) ?? `The API returned ${response.status}.`,
      response.status,
    )
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function detailOf(detail: string | Array<{ loc?: unknown[]; msg?: string }> | undefined) {
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail) || detail.length === 0) return null

  const first = detail[0]
  if (!first) return null

  const path = Array.isArray(first.loc) ? first.loc : []
  const field = path.length > 0 ? String(path[path.length - 1]) : null
  const message = first.msg?.replace(/^Value error, /, '') ?? 'is not valid'
  return field ? `${LABELS[field] ?? field}: ${message}` : message
}

/** Field names as the form spells them, not as the schema does. */
const LABELS: Record<string, string> = {
  name: 'Name',
  slug: 'URL name',
  primary_color: 'Primary colour',
  secondary_color: 'Secondary colour',
  voice_prompt: 'Voice',
  languages: 'Languages',
  font_choice: 'Headline face',
  products: 'What you sell',
  do_not_mention: 'Never mention',
  default_region_code: 'Default region',
}

export type BrandForm = {
  name: string
  slug: string
  voice_prompt: string
  primary_color: string
  secondary_color: string
  languages: string[]
  font_choice: string
  products: string[]
  default_region_code: string | null
  do_not_mention: string[]
}

export async function createBrand(form: BrandForm): Promise<Brand> {
  return send<Brand>('/brands', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    // An empty slug means "derive it from the name", which is what the API
    // does with a missing one. Sending "" would fail validation instead.
    body: JSON.stringify({ ...form, slug: form.slug || undefined }),
  })
}

export async function updateBrand(id: number, form: BrandForm): Promise<Brand> {
  return send<Brand>(`/brands/${id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ...form, slug: form.slug || undefined }),
  })
}

export async function deleteBrand(id: number, force = false): Promise<void> {
  await send<void>(`/brands/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' })
}

export async function uploadLogo(id: number, file: File): Promise<Brand> {
  const body = new FormData()
  body.append('file', file)
  // No content-type header: the browser has to set the multipart boundary.
  return send<Brand>(`/brands/${id}/logo`, { method: 'POST', body })
}

export async function removeLogo(id: number): Promise<Brand> {
  return send<Brand>(`/brands/${id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ logo_url: null }),
  })
}

/** The form's starting values for a brand, or for a new one. */
export function formOf(brand: Brand | null): BrandForm {
  return {
    name: brand?.name ?? '',
    slug: brand?.slug ?? '',
    voice_prompt: brand?.voice_prompt ?? '',
    primary_color: brand?.primary_color ?? '#1B2230',
    secondary_color: brand?.secondary_color ?? '#D8322B',
    languages: brand?.languages ?? ['english'],
    font_choice: brand?.font_choice ?? 'display',
    products: brand?.products ?? [],
    default_region_code: brand?.default_region_code ?? null,
    do_not_mention: brand?.do_not_mention ?? [],
  }
}

/**
 * Where ink stops being more readable than white.
 *
 * The luminance at which the contrast ratio against ink equals the ratio
 * against white. Mirrors `INK_THRESHOLD` in `app/images/pillow.py`, and the
 * derivation is written out there.
 */
const INK_THRESHOLD = 0.2131

/**
 * Ink or white, whichever is readable on `hex`.
 *
 * The same relative-luminance rule as `contrasting_ink` in the Pillow
 * templates, and deliberately the same threshold: the preview is a promise
 * about what the render will do, and two different rules would make it a
 * lie at exactly the colours a user is most likely to be unsure about.
 */
export function contrastingInk(hex: string): string {
  const value = hex.replace('#', '')
  const full = value.length === 3 ? [...value].map((c) => c + c).join('') : value
  const [r, g, b] = [0, 2, 4].map((i) => Number.parseInt(full.slice(i, i + 2), 16) / 255)
  if (r === undefined || g === undefined || b === undefined) return '#FFFFFF'
  if ([r, g, b].some(Number.isNaN)) return '#FFFFFF'

  const channel = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  const luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
  return luminance > INK_THRESHOLD ? '#1B2230' : '#FFFFFF'
}

/** A textarea's text as the list the API wants, and back. */
export const linesOf = (text: string): string[] =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

export const textOf = (lines: string[]): string => lines.join('\n')
