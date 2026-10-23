'use client'

import { useEffect, useState } from 'react'

import { formatIstTime } from '@/lib/format'

/**
 * IST wall clock. Rendered client-side and mounted empty on purpose: the
 * server's first paint would be a different minute than the client's, and
 * hydrating a mismatched time is a React error for no benefit. The reserved
 * width stops the bar from shifting when it fills in.
 */
export function IstClock() {
  const [now, setNow] = useState<string | null>(null)

  useEffect(() => {
    const tick = () => setNow(formatIstTime(new Date()))
    tick()
    const timer = setInterval(tick, 10_000)
    return () => clearInterval(timer)
  }, [])

  return (
    <span className="num inline-flex min-w-[5.5rem] justify-end text-sm text-ink" aria-live="off">
      {now ? `${now} IST` : ''}
    </span>
  )
}
