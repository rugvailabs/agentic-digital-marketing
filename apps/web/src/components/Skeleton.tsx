import { Card, Panel, cx } from '@/components/house'

/**
 * Skeletons, shaped like the thing that is coming.
 *
 * Not a spinner. A spinner says "wait" and a skeleton says "wait, and here
 * is roughly what you will get" — which on a page made of cards and a map
 * is the difference between a blank screen and a page mid-arrival. It also
 * holds the layout, so nothing jumps when the data lands.
 *
 * The sweep animation lives in globals.css as `.skeleton`, and it is the
 * only gradient in the system: it exists to be motion rather than
 * decoration, and it stops entirely under prefers-reduced-motion.
 *
 * Every one of these is aria-hidden with a live region beside it. A screen
 * reader should hear "loading", not forty empty boxes.
 */

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden="true" className={cx('skeleton block', className)} />
}

/** Wraps a set of skeletons so the wait is announced once. */
export function Loading({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  )
}

/** A line of text. `w` as a fraction, because a paragraph of equal-length
 *  lines reads as a barcode rather than as text. */
export function SkeletonText({ w = 'w-full', h = 'h-3' }: { w?: string; h?: string }) {
  return <Skeleton className={cx(h, w, 'rounded-sm')} />
}

/** The library's and dashboard's card grid. */
export function SkeletonCards({ count = 8 }: { count?: number }) {
  return (
    <Loading label="Loading your posts and reels">
      <ul className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: count }, (_, i) => (
          <li key={i}>
            <Card className="overflow-hidden">
              <Skeleton className="aspect-square w-full rounded-none" />
              <span className="flex flex-col gap-2 p-2.5">
                <SkeletonText w="w-11/12" />
                <SkeletonText w="w-2/3" h="h-2.5" />
                <SkeletonText w="w-1/2" h="h-2.5" />
              </span>
            </Card>
          </li>
        ))}
      </ul>
    </Loading>
  )
}

/** The library's list view, and anything else that is a stack of rows. */
export function SkeletonRows({ count = 6 }: { count?: number }) {
  return (
    <Loading label="Loading">
      <ul>
        {Array.from({ length: count }, (_, i) => (
          <li key={i} className="flex items-start gap-4 border-b border-dotted border-rule py-4">
            <Skeleton className="size-16 shrink-0 rounded-sm" />
            <span className="flex min-w-0 flex-1 flex-col gap-2">
              <SkeletonText w="w-2/3" />
              <SkeletonText w="w-1/2" h="h-2.5" />
              <SkeletonText w="w-1/3" h="h-2.5" />
            </span>
          </li>
        ))}
      </ul>
    </Loading>
  )
}

/**
 * The dashboard, whole.
 *
 * Shaped like the real page — map left, two panels right, work below —
 * because the dashboard is the one screen where the layout itself is the
 * information, and a generic block of grey would not prepare you for it.
 */
export function SkeletonDashboard() {
  return (
    <Loading label="Loading today's board">
      <div className="mx-auto max-w-[1400px] px-5 py-6">
        <SkeletonText w="w-32" h="h-6" />

        <div className="desk:grid-cols-[minmax(0,5fr)_minmax(0,4fr)] mt-5 grid gap-5">
          <Panel className="p-4">
            <SkeletonText w="w-48" h="h-3" />
            {/* The map's own aspect, so the panel does not resize under
                the reader when the real one arrives. */}
            <Skeleton className="mt-3 aspect-[1000/1100] w-full rounded-md" />
          </Panel>
          <div className="flex flex-col gap-5">
            {[0, 1].map((i) => (
              <Panel key={i} className="flex flex-col gap-3 p-4">
                <SkeletonText w="w-32" h="h-3" />
                {Array.from({ length: 5 }, (_, row) => (
                  <span key={row} className="flex items-center gap-3">
                    <Skeleton className="size-9 shrink-0 rounded-sm" />
                    <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                      <SkeletonText w="w-3/4" />
                      <SkeletonText w="w-1/3" h="h-2.5" />
                    </span>
                  </span>
                ))}
              </Panel>
            ))}
          </div>
        </div>

        <div className="desk:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] mt-5 grid gap-5">
          <Panel className="p-4">
            <SkeletonText w="w-36" h="h-3" />
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Array.from({ length: 4 }, (_, i) => (
                <Card key={i} className="overflow-hidden">
                  <Skeleton className="aspect-square w-full rounded-none" />
                  <span className="block p-2">
                    <SkeletonText w="w-5/6" h="h-2.5" />
                  </span>
                </Card>
              ))}
            </div>
          </Panel>
          <div className="flex flex-col gap-5">
            {[0, 1].map((i) => (
              <Panel key={i} className="flex flex-col gap-3 p-4">
                <SkeletonText w="w-28" h="h-3" />
                {Array.from({ length: 3 }, (_, row) => (
                  <SkeletonText key={row} w={row === 2 ? 'w-2/3' : 'w-full'} />
                ))}
              </Panel>
            ))}
          </div>
        </div>
      </div>
    </Loading>
  )
}

/** The brands grid: a header, three template thumbnails, a row of chips. */
export function SkeletonBrands({ count = 3 }: { count?: number }) {
  return (
    <Loading label="Loading your brands">
      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: count }, (_, i) => (
          <li key={i}>
            <Card className="overflow-hidden">
              <span className="flex items-center gap-3 p-3">
                <Skeleton className="size-8 shrink-0 rounded-sm" />
                <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <SkeletonText w="w-1/2" />
                  <SkeletonText w="w-1/3" h="h-2.5" />
                </span>
              </span>
              <span className="grid grid-cols-3 gap-2 border-y border-border bg-page p-3">
                {[0, 1, 2].map((t) => (
                  <Skeleton key={t} className="aspect-square w-full rounded-sm" />
                ))}
              </span>
              <span className="flex gap-1.5 p-3">
                {[0, 1, 2].map((c) => (
                  <Skeleton key={c} className="h-5 w-14 rounded-sm" />
                ))}
              </span>
            </Card>
          </li>
        ))}
      </ul>
    </Loading>
  )
}

/** The ladder, which is a column of rows with a big numeral at the left. */
export function SkeletonLadder({ count = 8 }: { count?: number }) {
  return (
    <Loading label="Loading the board">
      <ul>
        {Array.from({ length: count }, (_, i) => (
          <li key={i} className="rule-dotted flex items-start gap-3 px-4 py-4">
            <Skeleton className="h-10 w-9 shrink-0 rounded-sm" />
            <span className="flex min-w-0 flex-1 flex-col gap-2">
              <SkeletonText w={i % 3 === 0 ? 'w-11/12' : 'w-3/4'} />
              <SkeletonText w="w-1/4" h="h-2.5" />
            </span>
            <Skeleton className="h-4 w-14 shrink-0 rounded-sm" />
          </li>
        ))}
      </ul>
    </Loading>
  )
}
