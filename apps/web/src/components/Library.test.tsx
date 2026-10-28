import type { LibraryFacets, LibraryItem, LibraryPage } from '@trendforge/types'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Library } from './Library'

/** The row's own status buttons, as opposed to the filter chips that carry
 *  the same four words. */
const statusOf = (index = 0) => within(screen.getAllByRole('group', { name: 'Status' })[index]!)
const statusFilter = () => within(screen.getByRole('group', { name: 'Status filter' }))
const kindFilter = () => within(screen.getByRole('group', { name: 'Kind filter' }))

/**
 * The library list. What is worth testing here is the behaviour a user
 * would notice and a type checker would not: which link a row points at,
 * whether a status button writes the right PATCH, and whether a filter
 * reaches the API as a filter rather than as a page navigation.
 */

const fetchLibrary = vi.fn()
const moveJob = vi.fn()

vi.mock('./../lib/library', async () => {
  const actual = await vi.importActual<typeof import('./../lib/library')>('./../lib/library')
  return {
    ...actual,
    fetchLibrary: (...args: unknown[]) => fetchLibrary(...args),
    moveJob: (...args: unknown[]) => moveJob(...args),
  }
})

function item(over: Partial<LibraryItem> = {}): LibraryItem {
  return {
    id: 1,
    kind: 'post',
    language: 'english',
    formats: ['square'],
    status: 'ready',
    editorial_status: 'draft',
    scheduled_at: null,
    created_at: new Date().toISOString(),
    error: null,
    brand_id: 1,
    brand_name: 'Madras Filter Coffee',
    trend_id: 77,
    topic: 'India seal the series',
    region_code: 'IN-TN',
    region_name: 'Tamil Nadu',
    hook: 'India seal it in Chennai',
    preview_url: 'http://minio/square-poster.png',
    asset_count: 3,
    ...over,
  }
}

const page = (items: LibraryItem[], total = items.length): LibraryPage => ({
  items,
  total,
  limit: 50,
  offset: 0,
})

const facets: LibraryFacets = {
  brands: [{ id: 1, name: 'Madras Filter Coffee', count: 4 }],
  regions: [{ code: 'IN-TN', name: 'Tamil Nadu', count: 4 }],
  languages: ['english', 'tamil'],
  formats: ['square', 'reel'],
}

beforeEach(() => {
  fetchLibrary.mockReset()
  moveJob.mockReset()
  fetchLibrary.mockResolvedValue(page([item()]))
  moveJob.mockResolvedValue(undefined)
})

describe('Library', () => {
  it('a row opens its topic back in the Desk', () => {
    /** The Desk is where every action on an item lives, so the library
     *  links to the topic rather than to a detail page of its own. */
    render(<Library initial={page([item()])} facets={facets} />)

    const link = screen.getByRole('link', { name: 'India seal it in Chennai' })
    expect(link.getAttribute('href')).toBe('/board?region=IN-TN&topic=77')
  })

  it('shows the hook, with the topic under it', () => {
    render(<Library initial={page([item()])} facets={facets} />)

    expect(screen.getByText('India seal it in Chennai')).toBeInTheDocument()
    expect(screen.getByText('India seal the series')).toBeInTheDocument()
  })

  it('does not print the same line twice when there is no caption', () => {
    // A failed job has no hook, which falls back to the topic.
    render(<Library initial={page([item({ hook: null })])} facets={facets} />)

    expect(screen.getAllByText('India seal the series')).toHaveLength(1)
  })

  it('a failed item says why', () => {
    render(
      <Library
        initial={page([item({ status: 'failed', error: 'no model answered' })])}
        facets={facets}
      />,
    )

    expect(screen.getByText('no model answered')).toBeInTheDocument()
  })

  it('the current status is the pressed button and cannot be re-picked', () => {
    render(<Library initial={page([item({ editorial_status: 'approved' })])} facets={facets} />)

    const approved = statusOf().getByRole('button', { name: 'Approved' })
    expect(approved).toHaveAttribute('aria-pressed', 'true')
    expect(approved).toBeDisabled()
  })

  it('approving sends only the status', () => {
    render(<Library initial={page([item()])} facets={facets} />)

    fireEvent.click(statusOf().getByRole('button', { name: 'Approved' }))

    expect(moveJob).toHaveBeenCalledWith(1, { editorial_status: 'approved' })
  })

  it('scheduling sends a time, because the API requires one', () => {
    /** A scheduled row with no time is invisible on the calendar, which
     *  looks exactly like work that was lost. */
    render(<Library initial={page([item()])} facets={facets} />)

    fireEvent.click(statusOf().getByRole('button', { name: 'Scheduled' }))

    const [, change] = moveJob.mock.calls[0] as [number, Record<string, string>]
    expect(change.editorial_status).toBe('scheduled')
    expect(change.scheduled_at).toMatch(/^\d{4}-\d{2}-\d{2}T09:00:00\+05:30$/)
  })

  it('a filter refetches rather than navigating', async () => {
    render(<Library initial={page([item()])} facets={facets} />)

    fireEvent.click(kindFilter().getByRole('button', { name: 'Reels' }))

    await waitFor(() => expect(fetchLibrary).toHaveBeenCalled())
    expect(fetchLibrary.mock.calls.at(-1)?.[0]).toMatchObject({ kind: 'reel' })
  })

  it('picking a status chip twice clears it', async () => {
    render(<Library initial={page([item()])} facets={facets} />)

    fireEvent.click(statusFilter().getByRole('button', { name: 'Draft' }))
    await waitFor(() => expect(fetchLibrary).toHaveBeenCalled())
    fireEvent.click(statusFilter().getByRole('button', { name: 'Draft' }))

    await waitFor(() => expect(fetchLibrary.mock.calls.length).toBeGreaterThan(1))
    expect(fetchLibrary.mock.calls.at(-1)?.[0]).not.toHaveProperty('status')
  })

  it('says how many of how many when a page is partial', () => {
    render(<Library initial={page([item()], 340)} facets={facets} />)

    expect(screen.getByText('1 of 340 items')).toBeInTheDocument()
  })

  it('an empty library says what to do next', () => {
    render(<Library initial={page([])} facets={facets} />)

    expect(screen.getByText('No posts or reels yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'board' })).toBeInTheDocument()
  })

  it('an empty result under filters offers to clear them', async () => {
    fetchLibrary.mockResolvedValue(page([]))
    render(<Library initial={page([item()])} facets={facets} />)

    fireEvent.click(kindFilter().getByRole('button', { name: 'Reels' }))

    await waitFor(() =>
      expect(screen.getByText('Nothing matches those filters.')).toBeInTheDocument(),
    )
  })

  it('a filter with no values is disabled rather than empty', () => {
    render(
      <Library
        initial={page([item()])}
        facets={{ brands: [], regions: [], languages: [], formats: [] }}
      />,
    )

    expect(screen.getByLabelText('Brand')).toBeDisabled()
  })
})
