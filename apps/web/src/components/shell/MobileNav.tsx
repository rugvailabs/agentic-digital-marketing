'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { NAV, isActive } from '@/components/shell/nav'
import { cx } from '@/components/ui'

/**
 * The phone's navigation: a bottom bar, below the Desk breakpoint.
 *
 * Not a hamburger. The five destinations are the product, and a product
 * whose shape is behind a menu has no shape. A bottom bar also puts them
 * where a thumb is, which on the board — the page a user is on while
 * standing somewhere — is the whole difference.
 *
 * Rendered from the same NAV list as the sidebar, minus Settings, which
 * loses its place rather than crowding the bar to six.
 */
export function MobileNav() {
  const pathname = usePathname()
  const items = NAV.filter((item) => item.onPhone)

  return (
    <nav
      aria-label="Main"
      className={cx(
        'desk:hidden fixed inset-x-0 bottom-0 z-40 border-t border-border bg-panel',
        // Clears the home indicator on an installed PWA, where the bar sits
        // against the bottom edge of the screen rather than above browser
        // chrome.
        'pb-[env(safe-area-inset-bottom)]',
      )}
    >
      <ul className="grid grid-cols-5">
        {items.map((item) => {
          const active = isActive(pathname, item)
          const Icon = item.icon
          return (
            <li key={item.href} className="relative">
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={cx(
                  'flex h-14 flex-col items-center justify-center gap-1',
                  'transition-colors duration-150',
                  active ? 'text-ink' : 'text-muted',
                )}
              >
                <Icon aria-hidden="true" className="size-5" strokeWidth={2} />
                <span className="text-[11px] leading-none">{item.label}</span>
                {active ? (
                  <span
                    aria-hidden="true"
                    className="absolute top-0 h-0.5 w-10 rounded-full bg-chilli"
                  />
                ) : null}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
