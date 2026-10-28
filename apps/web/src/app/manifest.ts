import type { MetadataRoute } from 'next'

/**
 * The install manifest.
 *
 * A route rather than a static file, so the colours stay in one place with
 * the rest of the app's metadata and a palette change cannot leave the
 * splash screen on last month's grey.
 *
 * Installing matters here because of who this is for: a marketing team in
 * India working a trend is doing it on a phone, often away from a desk, and
 * "add to home screen" is the difference between opening the board in two
 * taps and hunting for a tab.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'TrendForge — trend desk for India',
    short_name: 'TrendForge',
    description:
      'What is trending across India and every state, ranked with hashtags, ready to post.',
    start_url: '/',
    // Standalone, not fullscreen: the board is a reading surface and the
    // status bar is where the clock lives. The app has its own IST clock in
    // the top bar, but a phone's own clock is what people check.
    display: 'standalone',
    orientation: 'portrait',
    // Paper, matching the light theme's ground. The splash screen appears
    // before any CSS does, so a white default would flash.
    background_color: '#eef1f6',
    theme_color: '#eef1f6',
    lang: 'en-IN',
    dir: 'ltr',
    categories: ['business', 'productivity', 'news'],
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      // Separate files, not the same ones listed twice: a maskable icon is
      // cropped to the launcher's shape, so its mark has to sit inside the
      // middle 80% and its ground has to run to the edge.
      {
        src: '/icons/maskable-192.png',
        sizes: '192x192',
        type: 'image/png',
        purpose: 'maskable',
      },
      {
        src: '/icons/maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
    shortcuts: [
      { name: 'Library', url: '/library' },
      { name: 'Calendar', url: '/calendar' },
    ],
  }
}
