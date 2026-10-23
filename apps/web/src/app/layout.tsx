import type { Metadata, Viewport } from 'next'
import { Bricolage_Grotesque, Schibsted_Grotesk } from 'next/font/google'
import type { ReactNode } from 'react'

import './globals.css'

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
}

export const viewport: Viewport = {
  // Both schemes are real designs, so let the OS pick.
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#eef1f6' },
    { media: '(prefers-color-scheme: dark)', color: '#121722' },
  ],
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-IN" className={`${display.variable} ${ui.variable}`}>
      <body>{children}</body>
    </html>
  )
}
