import Link from 'next/link'
import { notFound } from 'next/navigation'

import { BrandEditor } from '@/components/BrandEditor'
import { fetchBrand, fetchRegions } from '@/lib/api'

type Props = { params: Promise<{ id: string }> }

/**
 * Rendered per request, not at build time.
 *
 * Next prerenders a page with no dynamic inputs, and these all read the
 * API — so a build would either bake in whatever the board said that
 * afternoon or, with no API reachable, fail outright. Which is what it did.
 */
export const dynamic = 'force-dynamic'

export async function generateMetadata({ params }: Props) {
  const brand = await fetchBrand(Number((await params).id))
  return { title: brand ? `${brand.name} — TrendForge` : 'Brand — TrendForge' }
}

export default async function BrandPage({ params }: Props) {
  const id = Number((await params).id)
  if (!Number.isInteger(id)) notFound()

  const [brand, regions] = await Promise.all([fetchBrand(id), fetchRegions()])
  if (!brand) notFound()

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Link href="/brands" className="text-sm text-slate hover:text-ink">
        Back to brands
      </Link>

      <h1 className="mt-6 font-display text-[28px] leading-tight font-bold text-ink">
        {brand.name}
      </h1>
      <p className="mt-2 font-mono text-xs text-slate">{brand.slug}</p>

      <div className="mt-8">
        <BrandEditor brand={brand} regions={regions} />
      </div>
    </main>
  )
}
