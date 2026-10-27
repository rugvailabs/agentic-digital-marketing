import type { Platform, SourceName } from '@trendforge/types'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PlatformStrip } from './PlatformStrip'

const push = vi.fn()

vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))

function platform(name: SourceName, over: Partial<Platform> = {}): Platform {
  return {
    name,
    label: name,
    configured: true,
    env_vars: [],
    weight: 1,
    ...over,
  }
}

const ALL: Platform[] = [
  platform('google_trends'),
  platform('google_news'),
  platform('youtube'),
  platform('reddit', {
    configured: false,
    env_vars: ['REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET'],
  }),
  platform('x'),
  platform('instagram', { configured: false, env_vars: ['IG_ACCESS_TOKEN', 'IG_BUSINESS_ID'] }),
]

const COVERS: SourceName[] = ['google_trends', 'google_news']

beforeEach(() => push.mockClear())

describe('PlatformStrip', () => {
  it('offers All plus every platform, configured or not', () => {
    render(<PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" />)

    expect(screen.getByRole('tab', { name: 'All' })).toBeDefined()
    expect(screen.getByRole('tab', { name: /Trends/ })).toBeDefined()
    // Unconfigured platforms are still listed: an omitted chip reads as a
    // platform that does not exist rather than one needing a key.
    expect(screen.getByRole('tab', { name: /Reddit/ })).toBeDefined()
    expect(screen.getByRole('tab', { name: /Instagram/ })).toBeDefined()
  })

  it('marks All as selected when no platform filter is set', () => {
    render(<PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" />)

    expect(screen.getByRole('tab', { name: 'All' }).getAttribute('aria-selected')).toBe('true')
  })

  it('puts the chosen platform in the url and keeps the region', () => {
    render(<PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" />)

    fireEvent.click(screen.getByRole('tab', { name: /News/ }))

    expect(push).toHaveBeenCalledTimes(1)
    const url = String(push.mock.calls[0]?.[0])
    expect(url).toContain('platform=google_news')
    // Losing the region would silently throw the user back to India.
    expect(url).toContain('region=IN-MH')
  })

  it('clears the filter rather than setting platform=all', () => {
    render(
      <PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" selected="google_news" />,
    )

    fireEvent.click(screen.getByRole('tab', { name: 'All' }))

    const url = String(push.mock.calls[0]?.[0])
    expect(url).not.toContain('platform=')
    expect(url).toContain('region=IN-MH')
  })

  it('sends an unconfigured platform to settings instead of filtering', () => {
    render(<PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" />)

    const reddit = screen.getByRole('tab', { name: /Reddit/ })

    expect(reddit.getAttribute('href')).toBe('/settings')
    expect(reddit.getAttribute('title')).toContain('REDDIT_CLIENT_ID')
  })

  it('disables a platform that is configured but does not cover this region', () => {
    // YouTube's chart is country-level, so on a state board it is wired up
    // and still has nothing to show. Filtering by it would empty the ladder
    // with no explanation.
    render(<PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" />)

    const youtube = screen.getByRole('tab', { name: /YouTube/ })

    expect(youtube.getAttribute('aria-disabled')).toBe('true')
    expect(youtube.getAttribute('title')).toContain('no data for this region')

    fireEvent.click(youtube)
    expect(push).not.toHaveBeenCalled()
  })

  it('orders the platforms that cover this region first', () => {
    render(<PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" />)

    const names = screen.getAllByRole('tab').map((el) => el.textContent ?? '')

    // All, then the two that cover Maharashtra, then the rest.
    expect(names[0]).toBe('All')
    expect(names[1]).toMatch(/Trends|News/)
    expect(names[2]).toMatch(/Trends|News/)
  })

  it('keeps one tab stop for the whole strip', () => {
    // Roving tabindex, same as the region strip above it: arrows move within
    // the group, Tab leaves it.
    render(
      <PlatformStrip platforms={ALL} available={COVERS} region="IN-MH" selected="google_news" />,
    )

    const stops = screen.getAllByRole('tab').filter((el) => el.getAttribute('tabindex') === '0')

    expect(stops).toHaveLength(1)
    expect(stops[0]?.textContent).toMatch(/News/)
  })

  it('says so when the platform list could not be fetched', () => {
    // Never a real state — Trends and News need no credentials — so an
    // empty list means the API answered badly, and a bare "All" would read
    // as a deployment with no platforms at all.
    render(<PlatformStrip platforms={[]} available={[]} region="IN-MH" />)

    expect(screen.getAllByRole('tab')).toHaveLength(1)
    expect(screen.getByText('Platform list unavailable')).toBeDefined()
  })
})
