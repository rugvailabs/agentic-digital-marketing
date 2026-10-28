import { SkeletonDashboard } from '@/components/Skeleton'

/**
 * Shown while the dashboard's one request is in flight.
 *
 * Next renders this automatically for a server component that suspends,
 * so the whole page arrives shaped rather than blank — the dashboard
 * fetches a map, five movers, a week of work, three budgets and a
 * pipeline in one call, and that call is the slowest on the product.
 */
export default function Loading() {
  return <SkeletonDashboard />
}
