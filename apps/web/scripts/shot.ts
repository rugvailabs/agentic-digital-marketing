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
  /** Wait for a generated post to load, and frame the studio rather than the top. */
  studio?: boolean
  /** Select the row containing this text, rather than by position. */
  selectTopic?: string
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
    // The studio, showing posts generated live in three languages. Addressed
    // by topic text, not by rank: ranks move every time the curator runs, so
    // a rank here would silently screenshot a different topic next week.
    {
      name: 'studio-english',
      region: 'IN-GA',
      theme: 'light',
      viewport: DESKTOP,
      selectTopic: 'Al-Faisaly',
      studio: true,
    },
    {
      name: 'studio-hindi',
      region: 'IN-GA',
      theme: 'light',
      viewport: DESKTOP,
      selectTopic: 'Navy Weighs',
      studio: true,
    },
    {
      name: 'studio-tamil',
      region: 'IN-GA',
      theme: 'dark',
      viewport: DESKTOP,
      selectTopic: 'Goa weather',
      studio: true,
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

  // The dev server compiles a route on first request, which can take long
  // enough under networkidle to come back 500. Retry once; a second failure
  // is real and worth naming here rather than surfacing later as an
  // unexplained "selector never appeared".
  const url = `${BASE_URL}/?region=${encodeURIComponent(shot.region)}`
  let response = await page.goto(url, { waitUntil: 'networkidle' })
  if (response && !response.ok()) {
    console.log(`  ! ${shot.name}: ${response.status()} on a cold route, retrying`)
    await page.waitForTimeout(3000)
    response = await page.goto(url, { waitUntil: 'networkidle' })
  }
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
  // shot can catch the bar mid-hydration and ship a board with no clock. Soft
  // on purpose: a late clock is cosmetic, and failing the whole run over it
  // throws away the shots that did work.
  try {
    await page.waitForFunction(
      () => document.querySelector('header')?.textContent?.includes('IST') ?? false,
      undefined,
      { timeout: 15_000 },
    )
  } catch {
    // stdout, not stderr: this is a note, and a stderr write makes the
    // whole run look failed to a shell that watches it.
    console.log(`  ! ${shot.name}: clock had not painted; capturing anyway`)
  }
  const rows = await page.locator('[role="option"]').count()
  if (rows === 0) {
    throw new Error(`no topics for ${shot.region}: run \`.\\tf.ps1 ingest\` first`)
  }

  if (shot.selectTopic) {
    const row = page.locator('[role="option"]').filter({ hasText: shot.selectTopic }).first()
    if ((await row.count()) === 0) {
      throw new Error(`no row matching "${shot.selectTopic}" in ${shot.region}`)
    }
    await row.scrollIntoViewIfNeeded()
    await row.click()
  } else if (shot.selectRank) {
    await page.locator('[role="option"]').nth(shot.selectRank - 1).click()
  }
  if (!shot.openPanel) {
    // Clicking a row opens the panel below the Desk breakpoint; close it again
    // so the narrow shots show the ladder rather than the panel covering it.
    const close = page.getByRole('button', { name: 'Back to ladder' })
    if (await close.isVisible().catch(() => false)) await close.click()
  }

  if (shot.studio) {
    // Wait for the stored post to arrive and its images to decode, or the
    // shot catches an empty studio that looks like nothing was generated.
    await page.waitForSelector('figure img', { timeout: 20_000 })
    await page.waitForFunction(
      () => [...document.querySelectorAll('figure img')].every((i) => (i as HTMLImageElement).complete),
      undefined,
      { timeout: 20_000 },
    )
    await page.locator('textarea').first().scrollIntoViewIfNeeded()
  }

  await page.waitForTimeout(SETTLE_MS)
  const path = join(OUT_DIR, `${shot.name}.png`)
  await page.screenshot({ path, fullPage: shot.studio === true })
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
      '- `studio-*` — the content studio with posts generated live by Gemini.',
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
