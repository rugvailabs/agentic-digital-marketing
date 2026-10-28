/**
 * Does the calendar actually reschedule anything?
 *
 *   pnpm --filter @trendforge/web smoke:calendar
 *
 * Expects the stack up and the dev server running. Exits non-zero on any
 * failure, so it is usable as a gate.
 *
 * This exists because the two ways of moving an item are both the kind of
 * thing that passes a type check and a unit test and then does nothing in a
 * browser. Native HTML5 drag-and-drop silently refuses a drop when a
 * dragover handler forgets preventDefault, and a keyboard handler on a
 * non-focusable element never fires. Neither shows up anywhere but here.
 *
 * It schedules its own item and puts it back, so it can be run against a
 * working database without editing anyone's plan.
 */

import { chromium, type Page } from '@playwright/test'

const WEB = process.env.TRENDFORGE_WEB_URL ?? 'http://127.0.0.1:3020'
const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

type Job = { id: number; editorial_status: string; scheduled_at: string | null }
type Item = { id: number; topic: string; hook: string | null; scheduled_at: string | null }

const failures: string[] = []

function check(ok: boolean, message: string): void {
  console.log(`  ${ok ? '✓' : '✗'} ${message}`)
  if (!ok) failures.push(message)
}

async function job(id: number): Promise<Job> {
  const response = await fetch(`${API}/content/jobs/${id}`)
  if (!response.ok) throw new Error(`GET /content/jobs/${id} -> ${response.status}`)
  return (await response.json()) as Job
}

async function patch(id: number, body: Record<string, unknown>): Promise<void> {
  const response = await fetch(`${API}/content/jobs/${id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`PATCH /content/jobs/${id} -> ${response.status}`)
}

/** The IST day an instant falls on. */
function istDay(instant: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(instant))
}

/** A day comfortably inside the current month's grid, and the day before it. */
function midMonth(): { day: string; previous: string } {
  const now = new Date()
  const month = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}`
  return { day: `${month}-15`, previous: `${month}-14` }
}

async function pickItem(): Promise<Item> {
  const response = await fetch(`${API}/library?limit=1`)
  const page = (await response.json()) as { items: Item[] }
  const item = page.items[0]
  if (!item) throw new Error('nothing in the library to schedule')
  return item
}

async function itemOn(page: Page, title: string) {
  // `exact` defaults to false, so this is a case-insensitive substring
  // match on the accessible name — which is the title plus its time.
  return page.getByRole('button', { name: title }).first()
}

/**
 * Load the calendar and wait until it is hydrated.
 *
 * The text appears during SSR, so `waitForSelector` alone returns before
 * React has attached anything — focus set at that moment is dropped when
 * hydration re-renders, and the key press that follows goes to the body.
 * That cost an hour the first time: the handler was fine and the test was
 * pressing a key at nobody. Toggling the view is a client-only action, so
 * seeing it work proves the page is live.
 */
async function open(page: Page, title: string): Promise<void> {
  await page.goto(`${WEB}/calendar`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector(`text=${title}`, { timeout: 60_000 })

  // Clicked in a loop rather than once: a click before hydration is
  // actionable — the button is there, visible and enabled — and does
  // nothing at all, so waiting on its effect after a single click just
  // times out. Retrying is the only honest way to ask "are you live yet".
  const pressed = () =>
    page.locator('[aria-label="View"] [aria-pressed="true"]').innerText().catch(() => '')

  for (let attempt = 0; attempt < 30; attempt++) {
    await page.getByRole('button', { name: 'week', exact: true }).click()
    await page.waitForTimeout(500)
    if ((await pressed()).toLowerCase() === 'week') break
    if (attempt === 29) throw new Error('the calendar never hydrated')
  }

  await page.getByRole('button', { name: 'month', exact: true }).click()
  await page.waitForSelector(`text=${title}`, { timeout: 30_000 })
}

/** The day cell containing a given numeral. */
async function cellFor(page: Page, day: string) {
  const numeral = String(Number(day.slice(-2)))
  return page.locator('div.min-h-28', { has: page.getByText(numeral, { exact: true }) }).first()
}

async function main(): Promise<void> {
  const item = await pickItem()
  const original = await job(item.id)
  const { day, previous } = midMonth()
  const title = (item.hook ?? item.topic).slice(0, 28)

  console.log(`Calendar smoke on job ${item.id} — "${title}"`)

  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } })

  try {
    await patch(item.id, {
      editorial_status: 'scheduled',
      scheduled_at: `${day}T11:00:00+05:30`,
    })

    await open(page, title)
    check(true, 'the scheduled item appears on the grid')

    // ── drag ────────────────────────────────────────────────────────────
    await (await itemOn(page, title)).dragTo(await cellFor(page, previous))
    await page.waitForTimeout(1_500)

    const dragged = await job(item.id)
    check(istDay(dragged.scheduled_at!) === previous, `drag moved it to ${previous}`)
    check(
      dragged.scheduled_at!.includes('T05:30') || istHour(dragged.scheduled_at!) === '11',
      'drag kept the time of day',
    )
    check(dragged.editorial_status === 'scheduled', 'drag left it scheduled')

    // ── keyboard ────────────────────────────────────────────────────────
    await page.reload({ waitUntil: 'domcontentloaded' })
    await open(page, title)
    await (await itemOn(page, title)).focus()
    await page.keyboard.press('ArrowRight')
    await page.waitForTimeout(1_500)

    const keyed = await job(item.id)
    check(istDay(keyed.scheduled_at!) === day, `arrow key moved it back to ${day}`)

    const announced = await page.locator('[aria-live="polite"]').innerText()
    check(announced.length > 0, `the move is announced ("${announced.slice(0, 40)}…")`)

    // ── week view ───────────────────────────────────────────────────────
    await page.getByRole('button', { name: 'week', exact: true }).click()
    await page.waitForTimeout(1_500)
    check(
      await page.getByText(title, { exact: false }).first().isVisible(),
      'the week view shows it too',
    )
  } finally {
    await browser.close()
    await patch(item.id, {
      editorial_status: original.editorial_status,
      scheduled_at: original.scheduled_at,
    })
    console.log(`  restored job ${item.id} to ${original.editorial_status}`)
  }

  if (failures.length > 0) {
    console.error(`\n${failures.length} check(s) failed.`)
    process.exit(1)
  }
  console.log('\nCalendar smoke passed.')
}

function istHour(instant: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    hour12: false,
  }).format(new Date(instant))
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
