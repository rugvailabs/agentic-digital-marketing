import { SkeletonBrands } from '@/components/Skeleton'
import { SectionLabel } from '@/components/ui'

export default function Loading() {
  return (
    <div className="mx-auto max-w-[1400px] px-5 py-6">
      <h1 className="font-display text-xl font-bold text-ink">Brands</h1>
      <div className="mt-6">
        <SectionLabel>Loading</SectionLabel>
        <div className="mt-4">
          <SkeletonBrands />
        </div>
      </div>
    </div>
  )
}
