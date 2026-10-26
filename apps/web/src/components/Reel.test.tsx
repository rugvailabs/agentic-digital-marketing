import type { ContentJob } from '@trendforge/types'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Reel } from './Reel'

const SEGMENTS = [
  { kind: 'title', say: 'Here is the story trending in Goa today.', text: '', detail: '' },
  {
    kind: 'beat',
    say: 'The state signed off its artificial intelligence policy on Tuesday.',
    text: 'Goa has an AI policy',
    detail: 'Announced this week',
  },
  {
    kind: 'beat',
    say: 'There is a prize pool of two crore rupees for student teams.',
    text: '2 crore in prizes',
    detail: '',
  },
  { kind: 'outro', say: 'That is the Goa AI policy.', text: '', detail: '' },
]

function job(over: Partial<ContentJob> = {}): ContentJob {
  return {
    id: 7,
    trend_id: 42,
    brand_id: 1,
    kind: 'reel',
    language: 'english',
    formats: ['reel'],
    status: 'ready',
    error: null,
    assets: [],
    ...over,
  } as ContentJob
}

function scriptAsset(derived = false) {
  return {
    id: 1,
    kind: 'script',
    variant: 'english',
    url: null,
    edited: false,
    meta_json: { headline: 'Goa unveils AI policy', segments: SEGMENTS, derived },
  }
}

function videoAsset(over: Record<string, unknown> = {}) {
  return {
    id: 2,
    kind: 'video',
    variant: 'reel:wire',
    url: 'http://minio.test/jobs/7/reel-wire.mp4',
    edited: false,
    meta_json: {
      width: 1080,
      height: 1920,
      duration_seconds: 29.27,
      audio_codec: 'aac',
      voice: 'en-IN-NeerjaNeural',
      has_music: false,
      label: 'Reel',
      alt_text: 'A reel about the Goa AI policy.',
      ...over,
    },
  }
}

function setup(over: Partial<Parameters<typeof Reel>[0]> = {}) {
  const onRender = vi.fn()
  render(
    <Reel
      job={null}
      busy={false}
      error={null}
      onRender={onRender}
      blocked={false}
      disabled={false}
      {...over}
    />,
  )
  return { onRender }
}

describe('Reel', () => {
  it('says what the button will do before anything exists', () => {
    setup()

    expect(screen.getByRole('button', { name: 'Render reel' })).toBeInTheDocument()
    expect(screen.getByText(/narrated vertical video/i)).toBeInTheDocument()
  })

  it('starts a render when pressed', () => {
    const { onRender } = setup()

    fireEvent.click(screen.getByRole('button', { name: 'Render reel' }))

    expect(onRender).toHaveBeenCalledTimes(1)
  })

  it('sets the expectation that this takes minutes', () => {
    // Without this the first run looks stuck: a reel narrates, renders every
    // frame through a browser, then mixes.
    setup({ busy: true })

    expect(screen.getByText(/a few minutes/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rendering' })).toBeDisabled()
  })

  it('names the stage a reel is actually at', () => {
    setup({ job: job({ status: 'voicing' }), busy: true })

    expect(screen.getByText('Recording the voiceover')).toBeInTheDocument()
  })

  it('shows the script while the frames are still rendering', () => {
    // The script is written minutes before the video exists, so there is
    // something to read and correct rather than a spinner.
    setup({
      job: job({ status: 'rendering', assets: [scriptAsset()] as ContentJob['assets'] }),
      busy: true,
    })

    expect(screen.getByText(/script, while the frames render/i)).toBeInTheDocument()
    expect(screen.getByText('Goa has an AI policy')).toBeInTheDocument()
  })

  it('shows the card and the spoken line as separate things', () => {
    // They are deliberately different — the card carries "2 crore", the voice
    // carries "two crore rupees" — and both have to be checkable.
    setup({ job: job({ assets: [scriptAsset(), videoAsset()] as ContentJob['assets'] }) })

    expect(screen.getByText('2 crore in prizes')).toBeInTheDocument()
    expect(screen.getByText(/two crore rupees for student teams/)).toBeInTheDocument()
  })

  it('names each card by its position', () => {
    setup({ job: job({ assets: [scriptAsset()] as ContentJob['assets'] }) })

    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('Beat 1')).toBeInTheDocument()
    expect(screen.getByText('Beat 2')).toBeInTheDocument()
    expect(screen.getByText('Close')).toBeInTheDocument()
  })

  it('says when a script was built from the topic rather than written', () => {
    setup({ job: job({ assets: [scriptAsset(true)] as ContentJob['assets'] }) })

    expect(screen.getByText(/built from the topic, not written/i)).toBeInTheDocument()
  })

  it('does not claim a writer wrote a script it did write', () => {
    setup({ job: job({ assets: [scriptAsset(false)] as ContentJob['assets'] }) })

    expect(screen.queryByText(/built from the topic/i)).not.toBeInTheDocument()
  })

  it('plays the finished file and reports what is in it', () => {
    setup({ job: job({ assets: [videoAsset()] as ContentJob['assets'] }) })

    const video = screen.getByLabelText('A reel about the Goa AI policy.')
    expect(video).toHaveAttribute('src', 'http://minio.test/jobs/7/reel-wire.mp4')
    expect(video).toHaveAttribute('controls')
    expect(screen.getByText(/1080×1920 · 29.3s/)).toBeInTheDocument()
    expect(screen.getByText(/en-IN-NeerjaNeural/)).toBeInTheDocument()
  })

  it('says when a reel carries music', () => {
    setup({ job: job({ assets: [videoAsset({ has_music: true })] as ContentJob['assets'] }) })

    expect(screen.getByText(/· music/)).toBeInTheDocument()
  })

  it('offers the file for download', () => {
    setup({ job: job({ assets: [videoAsset()] as ContentJob['assets'] }) })

    expect(screen.getByRole('link', { name: 'Save MP4' })).toHaveAttribute(
      'href',
      'http://minio.test/jobs/7/reel-wire.mp4',
    )
  })

  it('offers a re-render once one exists', () => {
    setup({ job: job({ assets: [videoAsset()] as ContentJob['assets'] }) })

    expect(screen.getByRole('button', { name: 'Render again' })).toBeInTheDocument()
  })

  it('shows the pipeline failure verbatim with a way back', () => {
    const { onRender } = setup({
      job: job({ status: 'failed', error: 'The voice service did not answer within 60s.' }),
    })

    expect(screen.getByText('The voice service did not answer within 60s.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRender).toHaveBeenCalled()
  })

  it('refuses a topic the curator flagged', () => {
    setup({ blocked: true })

    expect(screen.getByRole('button', { name: 'Render reel' })).toBeDisabled()
    expect(screen.getByText(/do not market against/i)).toBeInTheDocument()
  })

  it('cannot render without a brand to render for', () => {
    setup({ disabled: true })

    expect(screen.getByRole('button', { name: 'Render reel' })).toBeDisabled()
  })
})
