import type { Brand } from '@trendforge/types'
import Link from 'next/link'

import { Empty, SectionLabel } from '@/components/ui'
import { fetchBrands } from '@/lib/api'

/**
 * Rendered per request, not at build time.
 *
 * Next prerenders a page with no dynamic inputs, and these all read the
 * API — so a build would either bake in whatever the board said that
 * afternoon or, with no API reachable, fail outright. Which is what it did.
 */
export const dynamic = 'force-dynamic'

export const metadata = { title: 'Brands — TrendForge' }

/**
 * Every brand in the workspace.
 *
 * A list rather than a grid of cards: cards are for generated assets, per
 * CLAUDE.md, and a brand is a row of facts. The swatches are the only colour
 * on the page and they are the brand's own, which is the one thing a user is
 * scanning for.
 */
export default async function BrandsPage() {
  const brands = await fetchBrands()

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <div className="mt-6 flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-[28px] leading-tight font-bold text-ink">Brands</h1>
        <Link
          href="/brands/new"
          className="border border-ink bg-ink px-3.5 py-1.5 text-sm text-page"
        >
          New brand
        </Link>
      </div>
      <p className="mt-2 max-w-prose text-sm text-slate">
        A brand carries the voice a caption is written in and the colours and logo every post and
        reel is drawn with.
      </p>

      <section className="mt-8">
        <SectionLabel>{brands.length === 1 ? '1 brand' : `${brands.length} brands`}</SectionLabel>
        {brands.length === 0 ? (
          <div className="mt-3">
            <Empty
              title="No brands yet."
              hint={
                <>
                  <Link href="/brands/new" className="text-ink underline underline-offset-2">
                    Create one
                  </Link>{' '}
                  to start generating posts.
                </>
              }
            />
          </div>
        ) : (
          <ul className="mt-3">
            {brands.map((brand) => (
              <li key={brand.id} className="border-b border-dotted border-rule">
                <Link
                  href={`/brands/${brand.id}`}
                  className="flex flex-wrap items-center gap-x-5 gap-y-2 py-3.5 hover:bg-row-hover"
                >
                  <span className="flex shrink-0 gap-1" aria-hidden="true">
                    <span
                      className="block h-7 w-7 border border-border"
                      style={{ backgroundColor: brand.primary_color }}
                    />
                    <span
                      className="block h-7 w-7 border border-border"
                      style={{ backgroundColor: brand.secondary_color }}
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-base text-ink">{brand.name}</span>
                    {/* Plain prose rather than fields strung on middle dots,
                        which CLAUDE.md rules out. */}
                    <span className="block truncate text-xs text-slate">{summarise(brand)}</span>
                  </span>
                  <span className="shrink-0 font-mono text-xs text-slate">{brand.slug}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}

/** One readable line: languages, whether there is a logo, where it opens. */
function summarise(brand: Brand): string {
  const parts = [
    brand.languages.length === 1
      ? `Writes in ${brand.languages[0]}`
      : `Writes in ${brand.languages.length} languages`,
  ]
  if (brand.logo_url) parts.push('has a logo')
  if (brand.default_region_code) parts.push(`opens on ${brand.default_region_code}`)
  return parts.join(', ')
}
