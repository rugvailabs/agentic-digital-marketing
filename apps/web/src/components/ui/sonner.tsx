'use client'

import { useEffect, useState } from 'react'

import { Toaster as Sonner, type ToasterProps } from 'sonner'
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
} from 'lucide-react'

/**
 * Vendored, with one change: the theme comes from our attribute.
 *
 * shadcn's version reads `next-themes`, which this product does not use —
 * the theme is a `data-theme` attribute written by a head script before
 * first paint. With no provider above it `useTheme()` returns "system",
 * and sonner's "system" means `prefers-color-scheme`. So a user on a light
 * OS who chose dark here got a light toast on a dark page.
 */
const Toaster = ({ ...props }: ToasterProps) => {
  const theme = useChosenTheme()

  return (
    <Sonner
      theme={theme as ToasterProps['theme']}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          '--normal-bg': 'var(--popover)',
          '--normal-text': 'var(--popover-foreground)',
          '--normal-border': 'var(--border)',
          '--border-radius': 'var(--radius)',
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: 'cn-toast',
        },
      }}
      {...props}
    />
  )
}

/** The theme the user chose, which is the attribute on <html>. */
function useChosenTheme(): 'light' | 'dark' {
  // Dark until the effect runs: dark is the default, so a first paint that
  // assumes it is right far more often than one that assumes light, and
  // the toaster renders nothing before an effect has fired anyway.
  const [theme, setTheme] = useState<'light' | 'dark'>('dark')

  useEffect(() => {
    const read = () =>
      setTheme(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')
    read()
    // The sidebar toggle writes the attribute; without watching for it an
    // open toast keeps the palette it was born with.
    const observer = new MutationObserver(read)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    return () => observer.disconnect()
  }, [])

  return theme
}

export { Toaster }
