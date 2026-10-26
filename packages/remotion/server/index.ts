/**
 * The renderer service.
 *
 * Remotion needs Node and its own Chromium — around a gigabyte of it — which
 * has no business in the lean Python image that api, worker and beat share.
 * So it lives here, behind two endpoints, and the Python side talks to it
 * through the VideoProvider adapter. If this service is down, that adapter
 * reports itself unconfigured and a reel is refused with a reason rather than
 * failing halfway through.
 *
 *   GET  /health   -> { ok, compositions, bundled }
 *   POST /render   -> the mp4, as a binary body
 *
 * One render at a time. Each one drives a headless Chromium across every
 * frame; two at once on a laptop means both finish late and the machine is
 * unusable in between.
 */

import { randomUUID } from 'node:crypto'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

import { bundle } from '@remotion/bundler'
import { renderMedia, selectComposition } from '@remotion/renderer'
import express from 'express'

import { missingPropKeys } from '../src/props'

const PORT = Number(process.env.RENDERER_PORT ?? 3100)
const PUBLIC_DIR = process.env.REMOTION_PUBLIC_DIR
  ? resolve(process.env.REMOTION_PUBLIC_DIR)
  : resolve(process.cwd(), 'public')
const ENTRY = resolve(process.cwd(), 'src/index.ts')
/** Chromium instances. More is faster per render and much heavier. */
const CONCURRENCY = Number(process.env.REMOTION_CONCURRENCY ?? 2)
/** Refuse anything longer than this. A runaway props payload would otherwise
 *  occupy the single render slot for an hour. */
const MAX_FRAMES = Number(process.env.REMOTION_MAX_FRAMES ?? 60 * 30)

const COMPOSITIONS = new Set(['Reel', 'Square'])

const app = express()
app.use(express.json({ limit: '1mb' }))

let bundlePromise: Promise<string> | null = null
let bundleError: string | null = null

/** Bundled once and reused: webpack over the composition tree takes seconds,
 *  and it is identical for every render. */
function getBundle(): Promise<string> {
  bundlePromise ??= bundle({
    entryPoint: ENTRY,
    publicDir: PUBLIC_DIR,
    onProgress: (percent) => {
      if (percent === 100) console.log('[renderer] bundle ready')
    },
  }).catch((error: unknown) => {
    // Cleared so the next request retries rather than inheriting a failure
    // from a transient one (a font mount that was not ready at boot).
    bundlePromise = null
    bundleError = error instanceof Error ? error.message : String(error)
    throw error
  })
  return bundlePromise
}

let busy: Promise<unknown> = Promise.resolve()

/** Serialise renders without dropping requests: each one waits its turn. */
function queue<T>(task: () => Promise<T>): Promise<T> {
  const result = busy.then(task, task)
  busy = result.catch(() => undefined)
  return result
}

app.get('/health', (_request, response) => {
  response.json({
    ok: true,
    compositions: [...COMPOSITIONS],
    bundled: bundlePromise !== null && bundleError === null,
    error: bundleError,
  })
})

app.post('/render', (request, response) => {
  const body = request.body as { composition?: string; props?: Record<string, unknown> }
  const composition = body?.composition ?? 'Reel'
  const props = body?.props ?? {}

  if (!COMPOSITIONS.has(composition)) {
    response.status(422).json({ detail: `unknown composition ${composition}` })
    return
  }
  const frames = Number(props.durationInFrames ?? 0)
  if (frames > MAX_FRAMES) {
    response.status(422).json({ detail: `${frames} frames exceeds the ${MAX_FRAMES} cap` })
    return
  }

  // src/props.ts and VideoBrief.as_props() are two halves of one contract in
  // two languages, with no compiler between them. A missing key means they
  // have drifted, and saying which one beats rendering a reel full of
  // placeholder copy and leaving someone to notice.
  const missing = missingPropKeys(props)
  if (missing.length > 0) {
    response.status(422).json({
      detail: `props are missing ${missing.join(', ')} — src/props.ts and VideoBrief.as_props() have drifted`,
    })
    return
  }

  const id = randomUUID().slice(0, 8)
  void queue(async () => {
    const started = Date.now()
    let dir: string | null = null
    try {
      const serveUrl = await getBundle()
      const selected = await selectComposition({
        serveUrl,
        id: composition,
        inputProps: props,
      })

      dir = await mkdtemp(join(tmpdir(), 'tf-render-'))
      const output = join(dir, `${composition}.mp4`)

      await renderMedia({
        composition: selected,
        serveUrl,
        codec: 'h264',
        // yuv420p is what every social platform and every phone decoder
        // wants; the default 4:4:4 plays back green on some Android players.
        pixelFormat: 'yuv420p',
        outputLocation: output,
        inputProps: props,
        concurrency: CONCURRENCY,
        // Silent on purpose. The voiceover and the music bed are mixed in by
        // ffmpeg on the Python side, where the voice decides the length.
        muted: true,
        chromiumOptions: { gl: 'swangle' },
      })

      const mp4 = await readFile(output)
      console.log(
        `[renderer] ${id} ${composition} ${selected.width}x${selected.height} ` +
          `${selected.durationInFrames}f in ${Date.now() - started}ms, ${mp4.length} bytes`,
      )

      response
        .status(200)
        .set({
          'content-type': 'video/mp4',
          'content-length': String(mp4.length),
          'x-render-id': id,
          'x-duration-frames': String(selected.durationInFrames),
          'x-width': String(selected.width),
          'x-height': String(selected.height),
          'x-fps': String(selected.fps),
        })
        .send(mp4)
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error)
      console.error(`[renderer] ${id} failed after ${Date.now() - started}ms:`, message)
      if (!response.headersSent) {
        // Verbatim: this reaches the job row and then the Desk, and a
        // marketer can act on "font file not found" but not on "500".
        response.status(500).json({ detail: message.slice(0, 500) })
      }
    } finally {
      if (dir) await rm(dir, { recursive: true, force: true }).catch(() => undefined)
    }
  })
})

app.listen(PORT, () => {
  console.log(`[renderer] listening on ${PORT}, public dir ${PUBLIC_DIR}`)
  // Warm the bundle at boot so the first reel is not also the first webpack
  // run. Failure here is logged, not fatal: /health reports it and the next
  // render retries.
  void getBundle().catch(() => undefined)
})
