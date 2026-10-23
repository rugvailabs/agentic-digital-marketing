import type { Trend } from '@trendforge/types'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Ladder } from './Ladder'

function trend(rank: number, over: Partial<Trend> = {}): Trend {
  return {
    rank,
    topic: `Topic ${rank}`,
    category: 'Sports',
    hashtags: [`#Topic${rank}`],
    volume: 200000,
    velocity: [0, 0, 0, 0, 90, 100],
    sources: ['google_trends'],
    score: 100 - rank,
    updated_at: '2026-10-23T06:15:00Z',
    evidence: [],
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

  it('shows source chips only once a topic is corroborated', () => {
    render(
      <Ladder
        trends={[trend(1, { sources: ['google_trends', 'google_news', 'youtube'] })]}
        selectedRank={1}
        onSelect={() => {}}
      />,
    )

    expect(screen.getByText('Trends')).toBeDefined()
    expect(screen.getByText('News')).toBeDefined()
    expect(screen.getByText('YouTube')).toBeDefined()
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

  it('compacts volume and dashes it when absent', () => {
    render(
      <Ladder trends={[trend(1), trend(2, { volume: 0 })]} selectedRank={1} onSelect={() => {}} />,
    )

    expect(screen.getByText('2L')).toBeDefined()
    expect(screen.getByText('—')).toBeDefined()
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

    const strokes = [...container.querySelectorAll('polyline')].map((p) =>
      p.getAttribute('stroke'),
    )
    expect(strokes).toEqual([
      'var(--color-chilli)',
      'var(--color-slate)',
      'var(--color-neem)',
    ])
  })
})
