import { CalendarDays, LayoutDashboard, Library, Palette, Radio, Settings } from 'lucide-react'

/**
 * The navigation, once.
 *
 * The sidebar and the phone's bottom bar are two renderings of this list
 * and not two lists. They drifted the first time they were separate — the
 * phone bar was missing Settings for a day and nobody noticed, because
 * nothing fails when a nav item is absent.
 */

export type NavItem = {
  href: string
  label: string
  icon: typeof LayoutDashboard
  /** Match child routes too, so /brands/3 lights up Brands. */
  prefix?: boolean
  /** The phone bar has room for five, not six. */
  onPhone: boolean
}

export const NAV: NavItem[] = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard, onPhone: true },
  { href: '/board', label: 'Board', icon: Radio, prefix: true, onPhone: true },
  { href: '/library', label: 'Library', icon: Library, prefix: true, onPhone: true },
  { href: '/calendar', label: 'Calendar', icon: CalendarDays, prefix: true, onPhone: true },
  { href: '/brands', label: 'Brands', icon: Palette, prefix: true, onPhone: true },
  // Settings loses the phone bar rather than crowding it to six. It is
  // reachable from the dashboard, and it is the item a phone user wants
  // least often.
  { href: '/settings', label: 'Settings', icon: Settings, prefix: true, onPhone: false },
]

export function isActive(pathname: string, item: NavItem): boolean {
  return item.prefix
    ? pathname === item.href || pathname.startsWith(`${item.href}/`)
    : pathname === item.href
}
