/**
 * Is the app actually installable?
 *
 *   pnpm --filter @trendforge/web build
 *   pnpm --filter @trendforge/web start   # in another shell
 *   pnpm --filter @trendforge/web smoke:pwa
 *
 * Against a production server, not the dev one: the service worker is
 * registered in production only, so a dev run proves nothing about the half
 * of this that matters.
 *
 * The checks mirror what a browser requires before it offers to install —
 * a manifest it can parse, a 192 and a 512 icon that actually load, a
 * start_url that answers, a maskable icon so the launcher does not crop the
 * mark off, and a service worker with a fetch handler.
 */

import { chromium } from '@playwright/test'

const WEB = process.env.TRENDFORGE_WEB_URL ?? 'http://127.0.0.1:3020'

type Manifest = {
  name?: string
  short_name?: string
  start_url?: string
  display?: string
  background_color?: string
  theme_color?: string
  icons?: Array<{ src: string; sizes: string; type?: string; purpose?: string }>
}

const failures: string[] = []

function check(ok: boolean, message: string): void {
  console.log(`  ${ok ? '✓' : '✗'} ${message}`)
  if (!ok) failures.push(message)
}

async function main(): Promise<void> {
  console.log(`PWA smoke against ${WEB}`)

  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })

  try {
    await page.goto(WEB, { waitUntil: 'domcontentloaded', timeout: 60_000 })

    const href = await page.getAttribute('link[rel="manifest"]', 'href')
    check(Boolean(href), `the page links a manifest (${href})`)
    if (!href) return

    const response = await page.request.get(new URL(href, WEB).toString())
    check(response.ok(), `the manifest is served (${response.status()})`)

    const manifest = (await response.json()) as Manifest
    check(Boolean(manifest.name && manifest.short_name), 'it has a name and a short name')
    check(manifest.display === 'standalone', 'it asks for a standalone window')
    check(Boolean(manifest.background_color), 'it sets a background colour for the splash')
    check(Boolean(manifest.start_url), `start_url is set (${manifest.start_url})`)

    const start = await page.request.get(new URL(manifest.start_url ?? '/', WEB).toString())
    check(start.ok(), `start_url answers (${start.status()})`)

    const icons = manifest.icons ?? []
    const sizes = icons.map((icon) => icon.sizes)
    check(sizes.includes('192x192'), 'there is a 192px icon')
    check(sizes.includes('512x512'), 'there is a 512px icon')
    check(
      icons.some((icon) => icon.purpose?.includes('maskable')),
      'there is a maskable icon, so a launcher cannot crop the mark off',
    )

    for (const icon of icons) {
      const file = await page.request.get(new URL(icon.src, WEB).toString())
      check(file.ok(), `${icon.src} loads (${file.status()})`)
    }

    // The worker: registered, controlling, and with a fetch handler. A
    // worker without one is not enough for an install prompt, and is also
    // not enough for the offline page.
    const registered = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return 'no serviceWorker in navigator'
      const reg = await navigator.serviceWorker.getRegistration()
      if (!reg) return 'nothing registered'
      await navigator.serviceWorker.ready
      return reg.active?.scriptURL ?? 'registered but not active'
    })
    check(
      typeof registered === 'string' && registered.endsWith('/sw.js'),
      `a service worker is active (${registered})`,
    )

    const sw = await page.request.get(`${WEB}/sw.js`)
    check(sw.ok(), 'sw.js is served')
    check((await sw.text()).includes("addEventListener('fetch'"), 'it handles fetch')

    // And the offline page itself, which is the only thing the worker
    // caches.
    const offline = await page.request.get(`${WEB}/offline`)
    check(offline.ok(), '/offline answers')

    // 390px is the phone this is designed against. A horizontal scrollbar
    // there means something is wider than the screen.
    await page.goto(`${WEB}/library`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1_500)
    for (const path of ['/', '/library', '/calendar', '/brands']) {
      await page.goto(`${WEB}${path}`, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(1_000)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      check(overflow <= 1, `${path} fits 390px (overflows by ${overflow}px)`)
    }
  } finally {
    await browser.close()
  }

  if (failures.length > 0) {
    console.error(`\n${failures.length} check(s) failed.`)
    process.exit(1)
  }
  console.log('\nPWA smoke passed.')
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
