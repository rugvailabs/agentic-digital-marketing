import type { Platform } from '@trendforge/types'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'

import { PlatformFilter } from './PlatformFilter'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))

function platform(name: string, configured: boolean): Platform {
  return {
    name,
    label: name,
    configured,
    coverage: 'country',
    missing_env: configured ? [] : [`${name.toUpperCase()}_CLIENT_ID`],
  } as unknown as Platform
}

/** Everything the API knows about, in the order it happens to answer in. */
const ALL = [
  platform('google_news', true),
  platform('instagram', false),
  platform('google_trends', true),
  platform('reddit', false),
  platform('youtube', true),
  platform('x', true),
]

/** Configured *and* covering Maharashtra. YouTube is country-level, so it
 *  is wired up and still has nothing to show on a state board. */
const COVERS = ['google_trends', 'google_news', 'x'] as const

/** Wrapped, because the component uses tooltips and the shell is what
 *  provides them in the app. A bare render throws the same error a missing
 *  provider would throw in production, which is the point of mirroring it. */
function renderFilter(selected?: 'google_news') {
  return render(
    <TooltipProvider>
      <PlatformFilter platforms={ALL} available={[...COVERS]} region="IN-MH" selected={selected} />
    </TooltipProvider>,
  )
}

describe('PlatformFilter', () => {
  beforeEach(() => push.mockReset())

  it('offers All plus every platform, configured or not', () => {
    renderFilter()

    expect(screen.getByRole('radio', { name: 'All platforms' })).toBeDefined()
    expect(screen.getByRole('radio', { name: 'Trends' })).toBeDefined()
    // An omitted segment reads as a platform that does not exist, rather
    // than as one nobody has pasted a key for.
    expect(screen.getByRole('radio', { name: /Reddit/ })).toBeDefined()
    expect(screen.getByRole('radio', { name: /Instagram/ })).toBeDefined()
  })

  it('shows the two-letter marks, not the full names', () => {
    // Seven full labels needed about 600px and the column is 440, so the
    // old strip clipped mid-word at "Inst" and scrolled sideways. The marks
    // are the same abbreviation the ladder rows use.
    renderFilter()

    expect(screen.getByRole('radio', { name: 'Trends' }).textContent).toBe('GT')
    expect(screen.getByRole('radio', { name: 'X' }).textContent).toBe('X')
  })

  it('marks All as checked when no platform filter is set', () => {
    renderFilter()

    expect(screen.getByRole('radio', { name: 'All platforms' }).dataset.state).toBe('on')
  })

  it('puts the chosen platform in the url and keeps the region', () => {
    renderFilter()

    fireEvent.click(screen.getByRole('radio', { name: 'News' }))

    expect(push).toHaveBeenCalledTimes(1)
    const url = String(push.mock.calls[0]?.[0])
    expect(url).toContain('platform=google_news')
    // Losing the region would silently throw the user back to India.
    expect(url).toContain('region=IN-MH')
  })

  it('clears the filter rather than setting platform=all', () => {
    renderFilter('google_news')

    fireEvent.click(screen.getByRole('radio', { name: 'All platforms' }))

    const url = String(push.mock.calls[0]?.[0])
    expect(url).not.toContain('platform=')
    expect(url).toContain('region=IN-MH')
  })

  it('disables a platform that cannot be filtered by, and says why', () => {
    // Two reasons a platform is unusable — no credentials, or configured
    // but country-level on a state board — and one treatment, because to
    // the person looking at the ladder they are the same thing: a filter
    // that would empty it.
    renderFilter()

    const reddit = screen.getByRole('radio', { name: /Reddit/ })
    const youtube = screen.getByRole('radio', { name: /YouTube/ })

    expect(reddit).toBeDisabled()
    expect(youtube).toBeDisabled()
    expect(reddit.getAttribute('aria-label')).toContain('not connected')

    fireEvent.click(reddit)
    expect(push).not.toHaveBeenCalled()
  })

  it('orders the platforms by the pipeline, not by the response', () => {
    // Discovery sources first, then the places you post. ALL above is
    // deliberately shuffled, so a component that trusted the response
    // order would put Instagram second.
    renderFilter()

    const names = screen.getAllByRole('radio').map((el) => el.textContent ?? '')

    expect(names).toEqual(['All', 'GT', 'GN', 'YT', 'RD', 'X', 'IG'])
  })
})
