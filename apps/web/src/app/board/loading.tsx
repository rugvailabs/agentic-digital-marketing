import { SkeletonLadder } from '@/components/Skeleton'

/**
 * The board's two columns, while the ladder is fetched.
 *
 * Only the ladder gets bones. The Desk is empty until a topic is picked,
 * so a skeleton there would promise content that is not coming.
 */
export default function Loading() {
  return (
    <div className="desk:flex-row flex min-h-[calc(100dvh-var(--spacing-topbar))] flex-col">
      <div className="desk:w-wire desk:border-r flex w-full shrink-0 flex-col border-border">
        <div className="h-[6.5rem] border-b border-border" />
        <SkeletonLadder />
      </div>
    </div>
  )
}
