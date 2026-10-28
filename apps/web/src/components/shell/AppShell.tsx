import type { ReactNode } from 'react'

import { MobileNav } from '@/components/shell/MobileNav'
import { Sidebar } from '@/components/shell/Sidebar'
import { TopBar } from '@/components/shell/TopBar'

/**
 * Sidebar, top bar, content.
 *
 * Every page used to carry its own chrome, which meant there was none: the
 * board had a top bar, the library had a "back to the board" link, and the
 * brand editor had neither. The product had no shape you could learn.
 *
 * The content area is deliberately unopinionated about padding. The board
 * fills the viewport edge to edge and every other page is a measured
 * column, and a shell that decided for both would have to be fought by
 * one of them.
 */
export function AppShell({
  workspaceName,
  children,
}: {
  workspaceName: string
  children: ReactNode
}) {
  return (
    <>
      <Sidebar workspaceName={workspaceName} />
      {/*
       * Offset by the sidebar's width rather than laid out beside it. The
       * sidebar is fixed so that it does not scroll with a long library,
       * and a fixed element is out of flow — so the content has to be
       * pushed, and the push has to use the same variable the sidebar's
       * width does or the two disagree mid-transition.
       */}
      <div className="desk:pl-(--sidebar-w) min-h-dvh transition-[padding] duration-150">
        <TopBar />
        {/* The phone bar is 56px of fixed furniture at the bottom, so the
            last thing on every page would otherwise be under it. */}
        <main className="desk:pb-0 pb-14">{children}</main>
      </div>
      <MobileNav />
    </>
  )
}
