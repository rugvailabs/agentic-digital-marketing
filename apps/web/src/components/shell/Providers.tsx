'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'

import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

/**
 * The three things a vendored component expects to find above it.
 *
 * A client component, held at the shell rather than per page, because all
 * three are singletons: two query clients means two caches, two Toasters
 * means every toast appears twice.
 *
 * The QueryClient is built in state rather than at module scope. A module
 * constant is created once per server process and shared by every request,
 * which on a server-rendered page means one user's cache answering another
 * user's render.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // The board is a trend desk: a number that is thirty seconds
            // stale is fine, and refetching every mount would make moving
            // between tabs flash.
            staleTime: 30_000,
            // Off. A desk left open on a second monitor refetched the
            // whole board every time the window was touched.
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  )

  return (
    <QueryClientProvider client={client}>
      {/* Zero delay: a disabled platform's "Connect" tooltip is the only
          explanation of why the control cannot be pressed, and 700ms of
          waiting for it reads as the control being broken. */}
      <TooltipProvider delayDuration={0} skipDelayDuration={300}>
        {children}
        {/*
         * Toasts bottom-right, not top-centre. The top of this product is
         * a fixed bar with the clock and the pipeline health in it, and a
         * toast landing there covers the two things that say whether the
         * thing you just did worked.
         */}
        <Toaster position="bottom-right" closeButton richColors={false} />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
