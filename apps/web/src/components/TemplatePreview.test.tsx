import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TEMPLATES, TemplatePreview, type PreviewBrand } from './TemplatePreview'

/**
 * The preview is a promise about what the renderer will draw, so what is
 * worth testing is the places the two could quietly disagree: which colours
 * are used, and whether a logo replaces the wordmark the way the footer
 * does.
 */

const brand = (over: Partial<PreviewBrand> = {}): PreviewBrand => ({
  name: 'Madras Filter Coffee',
  logoUrl: null,
  primaryColor: '#2B1A12',
  secondaryColor: '#E3A51D',
  fontChoice: 'display',
  ...over,
})

/** jsdom normalises inline colours to rgb(). */
const rgb = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16))
  return `rgb(${r}, ${g}, ${b})`
}

describe('TemplatePreview', () => {
  it.each(TEMPLATES)('%s renders', (template) => {
    render(<TemplatePreview template={template} brand={brand()} />)

    expect(screen.getByRole('img', { name: new RegExp(template, 'i') })).toBeInTheDocument()
  })

  it('the poster ground is the primary colour', () => {
    const { container } = render(<TemplatePreview template="poster" brand={brand()} />)

    const grounds = [...container.querySelectorAll<HTMLElement>('div')].map(
      (node) => node.style.backgroundColor,
    )
    expect(grounds).toContain(rgb('#2B1A12'))
  })

  it('the split block is the secondary colour', () => {
    const { container } = render(<TemplatePreview template="split" brand={brand()} />)

    const grounds = [...container.querySelectorAll<HTMLElement>('div')].map(
      (node) => node.style.backgroundColor,
    )
    expect(grounds).toContain(rgb('#E3A51D'))
  })

  it.each(TEMPLATES)('%s shows the brand name when there is no logo', (template) => {
    render(<TemplatePreview template={template} brand={brand()} />)

    expect(screen.getByText('Madras Filter Coffee')).toBeInTheDocument()
  })

  it.each(TEMPLATES)('%s replaces the wordmark with the logo', (template) => {
    render(<TemplatePreview template={template} brand={brand({ logoUrl: 'blob:logo' })} />)

    // Exactly as the renderer does it: two marks for one brand in a 30px
    // footer is clutter, so the name goes when a logo arrives.
    expect(screen.queryByText('Madras Filter Coffee')).not.toBeInTheDocument()
  })

  it('an unnamed brand still says something', () => {
    render(<TemplatePreview template="wire" brand={brand({ name: '' })} />)

    expect(screen.getByText('Your brand')).toBeInTheDocument()
  })

  it('the headline face follows font_choice', () => {
    const display = render(<TemplatePreview template="wire" brand={brand()} />)
    const headline = display.getByText(/India seal the series/)
    expect(headline.style.fontFamily).toContain('--font-display')

    display.unmount()

    const ui = render(<TemplatePreview template="wire" brand={brand({ fontChoice: 'ui' })} />)
    expect(ui.getByText(/India seal the series/).style.fontFamily).toContain('--font-ui')
  })

  it('the wire sparkline is chilli, which means rising on the board too', () => {
    const { container } = render(<TemplatePreview template="wire" brand={brand()} />)

    const line = container.querySelector('polyline')
    expect(line?.getAttribute('stroke')).toBe('#D8322B')
  })

  it('the same sample copy is used whatever the brand', () => {
    /** Changing brand should change only the brand. */
    const first = render(<TemplatePreview template="poster" brand={brand()} />)
    const headline = first.getByText(/India seal the series/).textContent
    first.unmount()

    const second = render(
      <TemplatePreview template="poster" brand={brand({ name: 'Anna Stores' })} />,
    )
    expect(second.getByText(/India seal the series/).textContent).toBe(headline)
  })
})
