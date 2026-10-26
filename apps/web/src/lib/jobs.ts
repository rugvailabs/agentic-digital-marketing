'use client'

import type { ContentJob, JobKind } from '@trendforge/types'
import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * One content job, watched.
 *
 * Posts and reels are separate rows on separate pipelines, but they are
 * started, polled and reported the same way — so they share this rather than
 * two copies that drift apart the first time a status is added.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8020'

/** A job is terminal when it will not change again without a new request. */
const TERMINAL = new Set(['ready', 'failed'])
const POLL_MS = 2000

/**
 * How long to keep watching. A reel narrates, renders every frame through a
 * browser, then mixes — minutes, not seconds — where a post is one model call
 * and three images.
 */
const TIMEOUT_MS: Record<JobKind, number> = {
  post: 10 * 60 * 1000,
  reel: 25 * 60 * 1000,
}

export type JobState = {
  job: ContentJob | null
  /** Running, as far as this tab knows. */
  busy: boolean
  /** A transport failure, as opposed to `job.error` from the pipeline. */
  error: string | null
  start: (body: StartBody) => void
}

type StartBody = {
  brandId: number
  language: string
  formats?: string[]
}

export function useJob(trendId: number, kind: JobKind): JobState {
  const [job, setJob] = useState<ContentJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stop = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }, [])

  const poll = useCallback(
    async (id: number, deadline: number) => {
      try {
        const response = await fetch(`${API}/content/jobs/${id}`, { cache: 'no-store' })
        if (!response.ok) throw new Error(`job ${id} returned ${response.status}`)
        const next = (await response.json()) as ContentJob

        setJob(next)
        if (TERMINAL.has(next.status)) {
          setBusy(false)
          return
        }
        if (Date.now() > deadline) {
          setBusy(false)
          setError('Still running. The job keeps going — reload to check on it.')
          return
        }
        timer.current = setTimeout(() => void poll(id, deadline), POLL_MS)
      } catch (cause) {
        setBusy(false)
        setError(cause instanceof Error ? cause.message : 'Could not reach the API.')
      }
    },
    [setJob],
  )

  // Switching topic must not leave the previous topic's work on screen, and a
  // topic that already has one should show it rather than looking unused.
  useEffect(() => {
    let cancelled = false
    stop()
    setJob(null)
    setError(null)
    setBusy(false)

    void (async () => {
      try {
        const response = await fetch(`${API}/content/jobs?trend_id=${trendId}&kind=${kind}`, {
          cache: 'no-store',
        })
        if (!response.ok || cancelled) return
        const existing = (await response.json()) as ContentJob | null
        if (!existing || cancelled) return

        setJob(existing)
        // Picked up mid-flight — from another tab, or a reload during a
        // render. Watching it is better than showing a stalled status.
        if (!TERMINAL.has(existing.status)) {
          setBusy(true)
          void poll(existing.id, Date.now() + TIMEOUT_MS[kind])
        }
      } catch {
        // No previous job is the normal case; silence is correct here.
      }
    })()

    return () => {
      cancelled = true
      stop()
    }
  }, [trendId, kind, poll, stop])

  useEffect(() => stop, [stop])

  const start = useCallback(
    (body: StartBody) => {
      setBusy(true)
      setError(null)
      setJob(null)

      void (async () => {
        try {
          const response = await fetch(`${API}/content/jobs`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
              trend_id: trendId,
              brand_id: body.brandId,
              kind,
              language: body.language,
              ...(body.formats ? { formats: body.formats } : {}),
            }),
          })
          if (!response.ok) {
            const detail = (await response.json().catch(() => null)) as { detail?: string } | null
            throw new Error(detail?.detail ?? `The API returned ${response.status}.`)
          }
          const created = (await response.json()) as ContentJob
          setJob(created)
          void poll(created.id, Date.now() + TIMEOUT_MS[kind])
        } catch (cause) {
          setBusy(false)
          setError(cause instanceof Error ? cause.message : 'Could not start the job.')
        }
      })()
    },
    [trendId, kind, poll],
  )

  return { job, busy, error, start }
}

/**
 * What each status is called, per kind.
 *
 * A reel passes through stages a post never sees, and "Rendering" means two
 * different things to someone waiting: a post is drawing three images, a reel
 * is driving a browser across nine hundred frames. Saying which is the
 * difference between waiting and reloading.
 */
const POST_LABELS: Record<string, string> = {
  queued: 'Queued',
  writing: 'Writing the caption',
  rendering: 'Rendering images',
  ready: 'Ready',
  failed: 'Failed',
}

const REEL_LABELS: Record<string, string> = {
  queued: 'Queued',
  writing: 'Writing the script',
  voicing: 'Recording the voiceover',
  rendering: 'Rendering frames',
  ready: 'Ready',
  failed: 'Failed',
}

export function statusLabel(kind: JobKind, status: string): string {
  const labels = kind === 'reel' ? REEL_LABELS : POST_LABELS
  return labels[status] ?? status
}
