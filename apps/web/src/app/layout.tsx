import type { Metadata, Viewport } from 'next'
import { Bricolage_Grotesque, Schibsted_Grotesk } from 'next/font/google'
import type { ReactNode } from 'react'

import { ServiceWorker } from '@/components/ServiceWorker'
import { AppShell } from '@/components/shell/AppShell'
import { CHROME_SCRIPT } from '@/lib/chrome'

import './globals.css'

/** One workspace exists and there is no way to make another, so its name is
 *  a constant rather than a fetch that would make every page dynamic. */
const WORKSPACE = 'Default workspace'

/*
 * next/font, self-hosted at build time: no external stylesheet request, no
 * layout shift. Bricolage carries optical sizing, which the 64px rank numerals
 * depend on.
 */
const display = Bricolage_Grotesque({
  subsets: ['latin'],
  // Loaded as a variable font (no static weight list) so 500/700/800 all
  // resolve from one file and the `opsz` axis stays available — next/font
  // rejects `axes` alongside explicit weights.
  axes: ['opsz'],
  variable: '--font-bricolage',
  display: 'swap',
})

const ui = Schibsted_Grotesk({
  subsets: ['latin'],
  // Variable, like Bricolage: asking for static instances made next/font fail
  // to fetch it ("Cannot read properties of null") and silently fall back to a
  // system face, which is not a failure mode we can ship.
  variable: '--font-schibsted',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'TrendForge — trend desk for India',
  description:
    'What is trending across India and every state, ranked with hashtags, ready to post.',
  // iOS ignores the manifest's icons and reads this one instead.
  appleWebApp: { capable: true, title: 'TrendForge', statusBarStyle: 'default' },
  icons: {
    icon: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: '/icons/apple-touch-icon.png',
  },
}

export const viewport: Viewport = {
  // The board is a dense column and the Desk is a panel; letting a phone
  // zoom out to a 980px "desktop" layout makes both unreadable. User
  // scaling is deliberately left alone — pinch-zoom is an accessibility
  // feature, not a layout bug.
  width: 'device-width',
  initialScale: 1,
  // Dark, to match the default. The browser paints this behind the page
  // before any CSS lands, and a light bar above a dark app is the flash
  // the inline script below exists to prevent.
  themeColor: '#0d1219',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // suppressHydrationWarning because the script below writes data-theme
    // and data-sidebar onto this element before React sees it, which is
    // exactly the mismatch the warning is for and exactly what is wanted.
    <html lang="en-IN" className={`${display.variable} ${ui.variable}`} suppressHydrationWarning>
      <head>
        {/*
         * Before the first paint, not after hydration. Reading the stored
         * theme in an effect means every load is dark for a frame and then
         * light, which is the single most noticeable bug a themed app can
         * have.
         */}
        <script dangerouslySetInnerHTML={{ __html: CHROME_SCRIPT }} />
      </head>
      <body>
        <AppShell workspaceName={WORKSPACE}>{children}</AppShell>
        <ServiceWorker />
      </body>
    </html>
  )
}
