'use client'

import { Moon, PanelLeftClose, PanelLeftOpen, Sun } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

import { NAV, isActive } from '@/components/shell/nav'
import { cx } from '@/components/ui'
import { SIDEBAR_KEY, type Theme, applyTheme } from '@/lib/chrome'

/**
 * The left rail.
 *
 * 240px of labelled navigation, collapsible to a 56px strip of icons. Every
 * page had its own "back to the board" link before this, which meant the
 * product had no shape — you could only ever go back to where you came
 * from.
 *
 * Icons only here and on actions, per CLAUDE.md. A nav item is the one
 * place an icon earns its room: it is what the collapsed rail is made of,
 * and it is the only way a 56px strip can say "calendar".
 *
 * The expanded/collapsed state is carried on <html data-sidebar>, set by an
 * inline script before paint, and the width is a CSS variable off that
 * attribute. React never renders the width, so there is no frame where the
 * sidebar is the wrong size — which is what a useState would have given on
 * every single page load.
 */

export function Sidebar({ workspaceName }: { workspaceName: string }) {
  const pathname = usePathname()
  // Read after mount, not during render: the attribute is the truth and the
  // server has not seen it. Only aria-expanded and the toggle icon depend
  // on this, and both are allowed to be right one tick late — nothing
  // visual moves, because the width is CSS.
  const [railed, setRailed] = useState(false)
  const [theme, setTheme] = useState<Theme>('dark')

  useEffect(() => {
    setRailed(document.documentElement.dataset.sidebar === 'rail')
    setTheme(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')
  }, [])

  function toggleRail() {
    const next = !railed
    setRailed(next)
    document.documentElement.dataset.sidebar = next ? 'rail' : 'full'
    try {
      localStorage.setItem(SIDEBAR_KEY, next ? 'rail' : 'full')
    } catch {
      // Private mode, or storage full. The sidebar still works for this
      // session; it just forgets.
    }
  }

  function toggleTheme() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    applyTheme(next)
  }

  return (
    <nav
      aria-label="Main"
      className={cx(
        'fixed inset-y-0 left-0 z-40 hidden shrink-0 flex-col border-r border-border bg-panel desk:flex',
        'w-(--sidebar-w) transition-[width] duration-150',
      )}
    >
      {/* The masthead sits in the sidebar, not the top bar: the top bar is
          for the state of the system, and the name of the product is not
          state. */}
      <div className="flex h-topbar items-center gap-2.5 border-b border-border px-3">
        <span
          aria-hidden="true"
          className="rank-numeral grid size-7 shrink-0 place-items-center rounded-sm bg-ink text-base text-page"
        >
          1
        </span>
        <span className="sidebar-label font-display text-base font-extrabold tracking-tight text-ink">
          TrendForge
        </span>
      </div>

      <ul className="flex flex-1 flex-col gap-0.5 p-2">
        {NAV.map((item) => {
          const active = isActive(pathname, item)
          const Icon = item.icon
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                title={item.label}
                className={cx(
                  'flex h-9 items-center gap-3 rounded-sm px-2.5',
                  'transition-[background-color,color] duration-150',
                  active
                    ? 'bg-card text-ink shadow-card'
                    : 'text-slate hover:bg-row-hover hover:text-ink',
                )}
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" strokeWidth={2} />
                <span className="sidebar-label truncate text-sm">{item.label}</span>
                {/* The one chilli on the sidebar: which page you are on.
                    It is the only thing here that is not navigation. */}
                {active ? (
                  <span
                    aria-hidden="true"
                    className="ml-auto h-4 w-0.5 shrink-0 rounded-full bg-chilli"
                  />
                ) : null}
              </Link>
            </li>
          )
        })}
      </ul>

      <div className="flex flex-col gap-0.5 border-t border-border p-2">
        <button
          type="button"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
          className="flex h-9 items-center gap-3 rounded-sm px-2.5 text-slate transition-[background-color,color] duration-150 hover:bg-row-hover hover:text-ink"
        >
          {theme === 'dark' ? (
            <Sun aria-hidden="true" className="size-4 shrink-0" strokeWidth={2} />
          ) : (
            <Moon aria-hidden="true" className="size-4 shrink-0" strokeWidth={2} />
          )}
          <span className="sidebar-label truncate text-sm">
            {theme === 'dark' ? 'Light theme' : 'Dark theme'}
          </span>
        </button>

        <button
          type="button"
          onClick={toggleRail}
          aria-expanded={!railed}
          aria-controls="app-sidebar"
          title={railed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex h-9 items-center gap-3 rounded-sm px-2.5 text-slate transition-[background-color,color] duration-150 hover:bg-row-hover hover:text-ink"
        >
          {railed ? (
            <PanelLeftOpen aria-hidden="true" className="size-4 shrink-0" strokeWidth={2} />
          ) : (
            <PanelLeftClose aria-hidden="true" className="size-4 shrink-0" strokeWidth={2} />
          )}
          <span className="sidebar-label truncate text-sm">Collapse</span>
        </button>

        {/*
         * The workspace, at the bottom, where an account always is. One
         * workspace exists and there is no way to make another, so this is
         * an identity rather than a picker — and saying so plainly beats a
         * dropdown with one item in it that implies otherwise.
         */}
        <div
          className="mt-1 flex h-11 items-center gap-2.5 rounded-sm border border-border bg-card px-2"
          title={workspaceName}
        >
          <span
            aria-hidden="true"
            className="grid size-6 shrink-0 place-items-center rounded-sm bg-overlay text-xs font-semibold text-ink"
          >
            {workspaceName.slice(0, 1).toUpperCase()}
          </span>
          <span className="sidebar-label min-w-0">
            <span className="block truncate text-xs text-ink">{workspaceName}</span>
            <span className="block truncate text-xs text-muted">Workspace</span>
          </span>
        </div>
      </div>
    </nav>
  )
}
