import { Skeleton } from '@/components/Skeleton'
import { WEEKDAYS } from '@/lib/calendar'
import { SectionLabel } from '@/components/house'

export default function Loading() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-10" role="status" aria-busy="true">
      <span className="sr-only">Loading the calendar</span>
      <h1 className="font-display text-[28px] leading-tight font-bold text-ink">Calendar</h1>

      <div className="mt-6 grid grid-cols-7 border-b border-border pb-1.5">
        {WEEKDAYS.map((name) => (
          <SectionLabel key={name}>{name}</SectionLabel>
        ))}
      </div>
      {/* Five rows of seven, which is the shape of every month grid. */}
      <div className="grid grid-cols-7">
        {Array.from({ length: 35 }, (_, i) => (
          <div key={i} className="min-h-28 border-r border-b border-border p-1.5 last:border-r-0">
            <Skeleton className="h-5 w-6 rounded-sm" />
          </div>
        ))}
      </div>
    </div>
  )
}
