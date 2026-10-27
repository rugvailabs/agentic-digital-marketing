import type { Platform, SourceName, Trend, TrendPlatform } from '@trendforge/types'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Hashtags } from './Hashtags'

const writeText = vi.fn(() => Promise.resolve())

function platformRow(platform: SourceName, hashtags: string[]): TrendPlatform {
  return {
    platform,
    rank: 1,
    volume: 100,
    hashtags,
    url: null,
    seen_at: '2026-10-27T06:15:00Z',
  }
}

function trend(over: Partial<Trend> = {}): Trend {
  return {
    id: 1,
    rank: 1,
    topic: 'India win the series',
    category: 'Sports',
    hashtags: ['#IndiaWin', '#Cricket'],
    volume: 1,
    velocity: [0, 0, 0, 0, 0, 1],
    sources: ['google_trends'],
    score: 1,
    summary: null,
    why_trending: null,
    relevance_to_region: null,
    safety_flag: null,
    updated_at: '2026-10-27T06:15:00Z',
    evidence: [],
    platforms: [],
    ...over,
  }
}

function platform(name: SourceName, configured: boolean): Platform {
  return { name, label: name, configured, env_vars: [], weight: 1 }
}

beforeEach(() => {
  writeText.mockClear()
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
})

describe('Hashtags', () => {
  it('keeps each platform in its own group', () => {
    // The whole point: #AskIndia means nothing on Instagram, so one pooled
    // list would be wrong everywhere it is pasted.
    render(
      <Hashtags
        trend={trend({
          platforms: [
            platformRow('reddit', ['#AskIndia', '#Cricket']),
            platformRow('youtube', ['#INDvAUS']),
          ],
        })}
        platforms={[]}
      />,
    )

    expect(screen.getByText('#AskIndia')).toBeDefined()
    expect(screen.getByText('#INDvAUS')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Copy Reddit hashtags' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Copy YouTube hashtags' })).toBeDefined()
  })

  it('copies only that group, space separated, ready to paste', async () => {
    render(
      <Hashtags
        trend={trend({
          platforms: [
            platformRow('reddit', ['#AskIndia', '#Cricket']),
            platformRow('youtube', ['#INDvAUS']),
          ],
        })}
        platforms={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Copy Reddit hashtags' }))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith('#AskIndia #Cricket'))
    // Not the YouTube tag, and not the topic's own.
    expect(writeText).not.toHaveBeenCalledWith(expect.stringContaining('#INDvAUS'))
  })

  it('confirms the copy, then goes back to saying what it does', async () => {
    render(<Hashtags trend={trend()} platforms={[]} />)

    const button = screen.getByRole('button', { name: 'Copy Topic hashtags' })
    fireEvent.click(button)

    await waitFor(() => expect(button.textContent).toBe('Copied'))
  })

  it('falls back to a prompt when the clipboard is refused', async () => {
    // Insecure origins and some policies reject writeText. Doing nothing
    // would look like a broken button.
    writeText.mockRejectedValueOnce(new Error('denied'))
    const prompt = vi.spyOn(window, 'prompt').mockReturnValue(null)

    render(<Hashtags trend={trend()} platforms={[]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy Topic hashtags' }))

    await waitFor(() =>
      expect(prompt).toHaveBeenCalledWith(expect.any(String), '#IndiaWin #Cricket'),
    )
    prompt.mockRestore()
  })

  it('shows the topic hashtags first, unlabelled by platform', () => {
    render(<Hashtags trend={trend()} platforms={[]} />)

    expect(screen.getByText('Topic')).toBeDefined()
    expect(screen.getByText('#IndiaWin')).toBeDefined()
  })

  it('says Instagram is not measured yet once it is connected', () => {
    // It is measured on demand when a topic is opened — the weekly limit is
    // 30 unique tags, so a whole board would spend two thirds of a week.
    render(<Hashtags trend={trend()} platforms={[platform('instagram', true)]} />)

    expect(screen.getByText('Not measured yet')).toBeDefined()
  })

  it('stays quiet about Instagram while it has no credentials', () => {
    // "Not measured yet" would imply it is about to be.
    render(<Hashtags trend={trend()} platforms={[platform('instagram', false)]} />)

    expect(screen.queryByText('Not measured yet')).toBeNull()
  })

  it('drops the pending line once Instagram has been measured', () => {
    render(
      <Hashtags
        trend={trend({ platforms: [platformRow('instagram', ['#teamindia'])] })}
        platforms={[platform('instagram', true)]}
      />,
    )

    expect(screen.queryByText('Not measured yet')).toBeNull()
    expect(screen.getByText('#teamindia')).toBeDefined()
  })

  it('skips a platform that reported the topic but no tags', () => {
    // An empty group is a labelled row with nothing in it and a copy button
    // that copies nothing.
    render(
      <Hashtags trend={trend({ platforms: [platformRow('google_news', [])] })} platforms={[]} />,
    )

    expect(screen.queryByRole('button', { name: 'Copy News hashtags' })).toBeNull()
  })

  it('renders nothing at all when there is nothing to show', () => {
    const { container } = render(<Hashtags trend={trend({ hashtags: [] })} platforms={[]} />)

    expect(container.firstChild).toBeNull()
  })
})
