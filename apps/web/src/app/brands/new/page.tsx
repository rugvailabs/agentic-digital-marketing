import Link from 'next/link'

import { BrandEditor } from '@/components/BrandEditor'
import { fetchRegions } from '@/lib/api'

/**
 * Rendered per request, not at build time.
 *
 * Next prerenders a page with no dynamic inputs, and these all read the
 * API — so a build would either bake in whatever the board said that
 * afternoon or, with no API reachable, fail outright. Which is what it did.
 */
export const dynamic = 'force-dynamic'

export const metadata = { title: 'New brand — TrendForge' }

export default async function NewBrandPage() {
  const regions = await fetchRegions()

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Link href="/brands" className="text-sm text-slate hover:text-ink">
        Back to brands
      </Link>

      <h1 className="mt-6 font-display text-[28px] leading-tight font-bold text-ink">New brand</h1>
      <p className="mt-2 max-w-prose text-sm text-slate">
        A name is enough to start. Everything else can be filled in once you have seen what the
        posts look like.
      </p>

      <div className="mt-8">
        <BrandEditor brand={null} regions={regions} />
      </div>
    </main>
  )
}
