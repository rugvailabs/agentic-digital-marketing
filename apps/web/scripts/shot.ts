/**
 * Screenshot the board in light and dark at desktop and phone widths.
 *
 *   pnpm --filter @trendforge/web shot            # all shots
 *   pnpm --filter @trendforge/web shot -- --region IN-MH
 *
 * Expects the stack up (`.\tf.ps1 up`), at least one ingest cycle
 * (`.\tf.ps1 ingest`) and the dev server running (`.\tf.ps1 dev`).
 * Writes to apps/web/screenshots/.
 */

import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium, type Page } from '@playwright/test'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(HERE, '..', 'screenshots')

const BASE_URL = process.env.TRENDFORGE_WEB_URL ?? 'http://localhost:3020'
/** Blocks the one load-in animation from smearing a shot. */
const SETTLE_MS = 500

type Viewport = { width: number; height: number }

/** 1440 is the common laptop; 390 is below the 800px Desk breakpoint. */
const DESKTOP: Viewport = { width: 1440, height: 900 }
const PHONE: Viewport = { width: 390, height: 844 }

type Shot = {
  name: string
  region: string
  theme: 'light' | 'dark'
  viewport: Viewport
  /** Pick a lower row so the Desk shows a different topic than rank 1. */
  selectRank?: number
  /** Phone: tapping a row opens the Desk panel, which is the state worth seeing. */
  openPanel?: boolean
}

function shots(regionOverride?: string): Shot[] {
  const national = regionOverride ?? 'IN'
  const state = regionOverride ?? 'IN-MH'
  return [
    { name: 'board-1440-light', region: national, theme: 'light', viewport: DESKTOP },
    { name: 'board-1440-dark', region: national, theme: 'dark', viewport: DESKTOP },
    {
      name: 'board-state-1440-light',
      region: state,
      theme: 'light',
      viewport: DESKTOP,
      selectRank: 3,
    },
    {
      name: 'board-state-1440-dark',
      region: state,
      theme: 'dark',
      viewport: DESKTOP,
      selectRank: 3,
    },
    { name: 'board-390-light', region: national, theme: 'light', viewport: PHONE },
    { name: 'board-390-dark', region: national, theme: 'dark', viewport: PHONE },
    {
      name: 'panel-390-light',
      region: national,
      theme: 'light',
      viewport: PHONE,
      selectRank: 2,
      openPanel: true,
    },
    {
      name: 'panel-390-dark',
      region: national,
      theme: 'dark',
      viewport: PHONE,
      selectRank: 2,
      openPanel: true,
    },
  ]
}

async function capture(page: Page, shot: Shot): Promise<string> {
  await page.setViewportSize(shot.viewport)
  // data-theme wins over prefers-color-scheme in globals.css; emulating the
  // media feature too keeps next/font and ::selection consistent.
  await page.emulateMedia({ colorScheme: shot.theme })

  const response = await page.goto(`${BASE_URL}/?region=${encodeURIComponent(shot.region)}`, {
    waitUntil: 'networkidle',
  })
  // A dev-server recompile can briefly 500. Say so, rather than letting it
  // surface later as an unexplained "selector never appeared" timeout.
  if (response && !response.ok()) {
    throw new Error(`${BASE_URL} returned ${response.status()} — is \`.\\tf.ps1 dev\` ready?`)
  }

  // The dev overlay badge sits over the bottom-left of the ladder. Hiding its
  // custom element works regardless of Next version; `devIndicators: false` in
  // next.config does not remove this portal in 15.5.
  await page.addStyleTag({ content: 'nextjs-portal { display: none !important }' })

  // Fail loudly rather than shipping a screenshot of an empty board.
  await page.waitForSelector('[role="option"]', { timeout: 15_000 })

  // The IST clock mounts empty and fills in from an effect, so without this a
  // shot can catch the bar mid-hydration and ship a board with no clock.
  await page.waitForFunction(
    () => document.querySelector('header')?.textContent?.includes('IST') ?? false,
    undefined,
    { timeout: 10_000 },
  )
  const rows = await page.locator('[role="option"]').count()
  if (rows === 0) {
    throw new Error(`no topics for ${shot.region}: run \`.\\tf.ps1 ingest\` first`)
  }

  if (shot.selectRank) {
    await page.locator('[role="option"]').nth(shot.selectRank - 1).click()
  }
  if (!shot.openPanel) {
    // Clicking a row opens the panel below the Desk breakpoint; close it again
    // so the narrow shots show the ladder rather than the panel covering it.
    const close = page.getByRole('button', { name: 'Back to ladder' })
    if (await close.isVisible().catch(() => false)) await close.click()
  }

  await page.waitForTimeout(SETTLE_MS)
  const path = join(OUT_DIR, `${shot.name}.png`)
  await page.screenshot({ path, fullPage: false })
  return `${shot.name}.png (${shot.region}, ${shot.viewport.width}px, ${rows} rows)`
}

async function main(): Promise<void> {
  const regionArg = process.argv.indexOf('--region')
  const regionOverride = regionArg > -1 ? process.argv[regionArg + 1] : undefined

  await mkdir(OUT_DIR, { recursive: true })

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: DESKTOP,
    deviceScaleFactor: 2,
    locale: 'en-IN',
    timezoneId: 'Asia/Kolkata',
  })
  const page = await context.newPage()

  const written: string[] = []
  try {
    for (const shot of shots(regionOverride)) {
      written.push(await capture(page, shot))
      console.log(`  ✓ ${written.at(-1)}`)
    }
  } finally {
    await browser.close()
  }

  await writeFile(
    join(OUT_DIR, 'README.md'),
    [
      '# Board screenshots',
      '',
      'Generated by `pnpm --filter @trendforge/web shot` against live ingested data.',
      'Captured at 2x, locale en-IN, timezone Asia/Kolkata.',
      '',
      '- `board-1440-*` — the two-column board at 1440px.',
      '- `board-390-*` — the ladder full width below the 800px Desk breakpoint.',
      '- `panel-390-*` — the Desk as a slide-in panel over the ladder.',
      '',
      ...written.map((w) => `- ${w}`),
      '',
    ].join('\n'),
    'utf8',
  )
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error)
  process.exit(1)
})
