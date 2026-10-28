import type { Brand } from '@trendforge/types'
import { Plus } from 'lucide-react'
import Link from 'next/link'

import { TemplatePreview } from '@/components/TemplatePreview'
import { EmptyState } from '@/components/Empty'
import { ButtonLink, Card, Chip, SectionLabel } from '@/components/house'
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
 * Every brand in the workspace, as cards.
 *
 * This was a list of rows, on the reasoning that cards are for generated
 * assets and a brand is a row of facts. That was wrong about what a brand
 * is: a brand *is* a look, and "which one is this" can only be answered by
 * showing what it makes. Each card carries the three templates at
 * thumbnail size in that brand's colours, face and logo — the same preview
 * the editor shows beside the form, at a quarter of the size.
 */
export default async function BrandsPage() {
  const brands = await fetchBrands()

  return (
    <div className="mx-auto max-w-[1400px] px-5 py-6">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-ink">Brands</h1>
          <p className="mt-1.5 max-w-prose text-sm text-slate">
            A brand carries the voice a caption is written in, and the colours, face and logo every
            post and reel is drawn with.
          </p>
        </div>
        <ButtonLink href="/brands/new" variant="primary">
          <Plus aria-hidden="true" className="size-4" strokeWidth={2} />
          New brand
        </ButtonLink>
      </div>

      <section className="mt-6">
        <SectionLabel>{brands.length === 1 ? '1 brand' : `${brands.length} brands`}</SectionLabel>

        {brands.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              art="grid"
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
          <ul className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {brands.map((brand) => (
              <BrandCard key={brand.id} brand={brand} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function BrandCard({ brand }: { brand: Brand }) {
  const preview = {
    name: brand.name,
    logoUrl: brand.logo_url,
    primaryColor: brand.primary_color,
    secondaryColor: brand.secondary_color,
    fontChoice: brand.font_choice,
  }

  return (
    <li>
      <Card className="flex h-full flex-col overflow-hidden transition-[border-color] duration-150 hover:border-border-hover">
        <Link href={`/brands/${brand.id}`} className="flex h-full flex-col">
          <div className="flex items-center gap-3 p-3">
            {/* The logo where there is one, the swatches where there is
                not. Both answer "whose is this" at a glance, which is the
                only question a list of brands is ever asked. */}
            {brand.logo_url ? (
              /* A MinIO URL on a published port, which next/image cannot
                 be configured for without pinning the dev host. */
              // eslint-disable-next-line @next/next/no-img-element
              <img src={brand.logo_url} alt="" className="h-8 max-w-20 shrink-0 object-contain" />
            ) : (
              <span aria-hidden="true" className="flex shrink-0 gap-1">
                <span
                  className="block size-8 rounded-sm border border-border"
                  style={{ backgroundColor: brand.primary_color }}
                />
                <span
                  className="block size-8 rounded-sm border border-border"
                  style={{ backgroundColor: brand.secondary_color }}
                />
              </span>
            )}

            <span className="min-w-0 flex-1">
              <span className="block truncate text-base text-ink">{brand.name}</span>
              <span className="block truncate font-mono text-xs text-faint">{brand.slug}</span>
            </span>
          </div>

          {/* The three templates at a quarter size. A brand is a look, and
              this is the look. */}
          <div className="grid grid-cols-3 gap-2 border-y border-border bg-page p-3">
            <TemplatePreview template="poster" brand={preview} />
            <TemplatePreview template="split" brand={preview} />
            <TemplatePreview template="wire" brand={preview} />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 p-3">
            {brand.languages.slice(0, 4).map((language) => (
              <Chip key={language} className="capitalize">
                {language}
              </Chip>
            ))}
            {brand.languages.length > 4 ? <Chip>+{brand.languages.length - 4}</Chip> : null}
            {brand.default_region_code ? (
              <Chip tone="solid">{brand.default_region_code}</Chip>
            ) : null}
          </div>
        </Link>
      </Card>
    </li>
  )
}
