import type { Trend } from '@trendforge/types'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Ladder } from './Ladder'

function trend(rank: number, over: Partial<Trend> = {}): Trend {
  return {
    id: 100 + rank,
    rank,
    topic: `Topic ${rank}`,
    category: 'Sports',
    hashtags: [`#Topic${rank}`],
    volume: 200000,
    velocity: [0, 0, 0, 0, 90, 100],
    sources: ['google_trends'],
    score: 100 - rank,
    updated_at: '2026-10-23T06:15:00Z',
    summary: null,
    why_trending: null,
    relevance_to_region: null,
    safety_flag: null,
    evidence: [],
    platforms: [],
    ...over,
  }
}

const rows = [trend(1), trend(2), trend(3)]

describe('Ladder', () => {
  it('renders one option per topic with its rank numeral', () => {
    render(<Ladder trends={rows} selectedRank={1} onSelect={() => {}} />)

    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(3)
    expect(options[0]).toHaveAttribute('aria-selected', 'true')
    expect(options[1]).toHaveAttribute('aria-selected', 'false')
  })

  it('exposes the rank to screen readers, since the numeral itself is decorative', () => {
    render(<Ladder trends={rows} selectedRank={1} onSelect={() => {}} />)

    expect(screen.getByText('Rank 2:')).toBeDefined()
  })

  it('shows platform marks only once a topic is corroborated', () => {
    render(
      <Ladder
        trends={[trend(1, { sources: ['google_trends', 'google_news', 'youtube'] })]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    // Letter marks rather than words: six bordered chips do not fit a 420px
    // column, and CLAUDE.md rules out an icon beside every label.
    expect(screen.getByText('GT')).toBeDefined()
    expect(screen.getByText('GN')).toBeDefined()
    expect(screen.getByText('YT')).toBeDefined()
  })

  it('prefers the per-platform rows over sources, and names what each counted', () => {
    render(
      <Ladder
        trends={[
          trend(1, {
            sources: ['google_trends'],
            platforms: [
              {
                platform: 'reddit',
                rank: 2,
                volume: 18400,
                hashtags: ['#Cricket'],
                url: null,
                seen_at: '2026-10-27T06:15:00Z',
              },
              {
                platform: 'youtube',
                rank: 14,
                volume: 902000,
                hashtags: [],
                url: null,
                seen_at: '2026-10-27T06:15:00Z',
              },
            ],
          }),
        ]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    // The platform rows win: `sources` says Trends only, and the row shows
    // the two platforms that actually reported it.
    expect(screen.getByText('RD')).toBeDefined()
    expect(screen.getByText('YT')).toBeDefined()
    expect(screen.queryByText('GT')).toBeNull()

    // The unit is named, because 18,400 upvotes and 902,000 views are not
    // comparable and a bare number invites comparing them.
    expect(screen.getByLabelText('#2 on Reddit — 18,400 upvotes')).toBeDefined()
    expect(screen.getByLabelText('#14 on YouTube — 9,02,000 views')).toBeDefined()
  })

  it('hides the source chip on a single-source row, where it says nothing', () => {
    render(
      <Ladder
        trends={[trend(1, { sources: ['google_trends'] })]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    expect(screen.queryByText('Trends')).toBeNull()
    // The category chip is unaffected.
    expect(screen.getByText('Sports')).toBeDefined()
  })

  it('gives the top three ranks the headline numeral and the rest the small one', () => {
    const { container } = render(
      <Ladder trends={[trend(1), trend(3), trend(4)]} selectedRank={1} onSelect={() => {}} />,
    )

    const numerals = [...container.querySelectorAll('.rank-numeral')]
    expect(numerals[0]?.className).toContain('text-rank')
    expect(numerals[0]?.className).not.toContain('text-rank-sm')
    expect(numerals[1]?.className).not.toContain('text-rank-sm')
    expect(numerals[2]?.className).toContain('text-rank-sm')
  })

  it('never tints a rank numeral with the accent, including the selected row', () => {
    const { container } = render(
      <Ladder trends={[trend(1), trend(2)]} selectedRank={1} onSelect={() => {}} />,
    )

    // Chilli belongs to rising velocity alone.
    for (const numeral of container.querySelectorAll('.rank-numeral')) {
      expect(numeral.className).toContain('text-ink')
      expect(numeral.className).not.toContain('chilli')
    }
  })

  it('selects a row on click', () => {
    const onSelect = vi.fn()
    render(<Ladder trends={rows} selectedRank={1} onSelect={onSelect} />)

    fireEvent.click(screen.getAllByRole('option')[2]!)
    expect(onSelect).toHaveBeenCalledWith(3)
  })

  it('moves the selection with the arrow keys', () => {
    const onSelect = vi.fn()
    render(<Ladder trends={rows} selectedRank={2} onSelect={onSelect} />)
    const list = screen.getByRole('listbox')

    fireEvent.keyDown(list, { key: 'ArrowDown' })
    expect(onSelect).toHaveBeenLastCalledWith(3)

    fireEvent.keyDown(list, { key: 'ArrowUp' })
    expect(onSelect).toHaveBeenLastCalledWith(1)
  })

  it('jumps to the ends with Home and End', () => {
    const onSelect = vi.fn()
    render(<Ladder trends={rows} selectedRank={2} onSelect={onSelect} />)
    const list = screen.getByRole('listbox')

    fireEvent.keyDown(list, { key: 'End' })
    expect(onSelect).toHaveBeenLastCalledWith(3)

    fireEvent.keyDown(list, { key: 'Home' })
    expect(onSelect).toHaveBeenLastCalledWith(1)
  })

  it('does not run off either end of the ladder', () => {
    const onSelect = vi.fn()
    render(<Ladder trends={rows} selectedRank={1} onSelect={onSelect} />)

    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'ArrowUp' })
    expect(onSelect).toHaveBeenLastCalledWith(1)
  })

  it('keeps exactly one tab stop for the whole ladder', () => {
    render(<Ladder trends={rows} selectedRank={2} onSelect={() => {}} />)

    const tabbable = screen.getAllByRole('option').filter((o) => o.tabIndex === 0)
    expect(tabbable).toHaveLength(1)
  })

  it('compacts volume when a series exists', () => {
    render(<Ladder trends={[trend(1)]} selectedRank={1} onSelect={() => {}} />)

    expect(screen.getByText('2L')).toBeDefined()
  })

  it('names the source instead of a volume when there is no series', () => {
    // News and YouTube report no volume; a sparkline drawn from score alone
    // would invent a trend line out of ranking noise.
    render(
      <Ladder
        trends={[trend(1, { volume: 0, sources: ['google_news'] })]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    expect(screen.getByText('News')).toBeDefined()
    expect(screen.queryByText('—')).toBeNull()
  })

  it('draws no sparkline when there is no series', () => {
    const { container } = render(
      <Ladder
        trends={[trend(1, { volume: 0, sources: ['google_news'] })]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    expect(container.querySelectorAll('polyline')).toHaveLength(0)
  })

  it('clamps a long title to two lines rather than truncating to one', () => {
    const { container } = render(
      <Ladder
        trends={[trend(1, { topic: 'Rafale Marine fighter begins flight trials in Goa' })]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    const title = container.querySelector('p[title]')
    expect(title?.className).toContain('line-clamp:2')
    expect(title?.className).not.toContain('truncate')
  })

  it('gives every sparkline an accessible label naming the trend direction', () => {
    render(<Ladder trends={[trend(1)]} selectedRank={1} onSelect={() => {}} />)

    expect(screen.getByRole('img', { name: /Rising/ })).toBeDefined()
  })

  it('colours the sparkline to match the direction it reports', () => {
    const { container } = render(
      <Ladder
        trends={[
          trend(1, { velocity: [0, 0, 0, 0, 10, 90] }), // rising
          trend(2, { velocity: [50, 50, 50, 50, 50, 50] }), // flat
          trend(3, { velocity: [90, 80, 70, 60, 50, 5] }), // falling
        ]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    const strokes = [...container.querySelectorAll('polyline')].map((p) => p.getAttribute('stroke'))
    expect(strokes).toEqual(['var(--color-chilli)', 'var(--color-slate)', 'var(--color-neem)'])
  })
})
