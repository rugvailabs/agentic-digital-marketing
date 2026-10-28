import { SectionLabel } from '@/components/house'
import { SkeletonCards } from '@/components/Skeleton'

export default function Loading() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="font-display text-[28px] leading-tight font-bold text-ink">Library</h1>
      <div className="mt-8">
        <SectionLabel>Loading</SectionLabel>
        <div className="mt-4">
          <SkeletonCards />
        </div>
      </div>
    </div>
  )
}
