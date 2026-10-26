# @trendforge/remotion

Video templates, and the service that renders them.

| Composition | Size      | Use                        |
| ----------- | --------- | -------------------------- |
| `Reel`      | 1080×1920 | Instagram / YouTube Shorts |
| `Square`    | 1080×1080 | Feed post                  |

Both are the same component. A square is the reel with less vertical room, not
a second layout to keep in step — every size is a fraction of the canvas
width, the way the Pillow post templates do it.

## Why this is a separate service

Remotion drives a headless Chromium, around a gigabyte of it. The api, worker
and beat services share one lean Python image and have no use for a browser,
so the renderer gets its own image and the Python side talks to it over HTTP
through `app/video/remotion.py`. Swap that adapter and nothing above it
changes.

    GET  /health   -> { ok, compositions, bundled, error }
    POST /render   -> the mp4 as a binary body

One render at a time. Each drives a browser across every frame; two at once on
a laptop means both finish late and the machine is unusable in between.

## The props are a contract with Python

`src/props.ts` mirrors `VideoBrief.as_props()` in
`apps/api/app/video/base.py`. The Python side is the only producer and it is
in another language, so no compiler catches a rename: a test there pins the
key names and `props.ts` is the other half. **Change one, change both.**

Every field is re-checked in `withDefaults()` before it reaches a composition.
A missing `beats` array would otherwise be a stack trace in a headless
Chromium log rather than anything a user could act on.

`durationInFrames` is derived from the beats rather than taken on trust — a
value shorter than the beats truncates the last one, and a longer one holds a
frozen frame at the end. Both look like a broken render.

## How a card is laid out

`src/typography.ts` measures the wrapped lines with a canvas and returns the
largest size that fits the box. Nothing is a fixed fraction of the canvas, so
a three-word beat comes out enormous and a long one steps down and wraps —
which is where the scale contrast comes from, and why a new topic does not
need a new layout.

That has one consequence worth knowing: **nothing may be drawn before the
faces are loaded.** Measuring against a fallback builds a layout for a font
that is not the one it renders in. `useFonts()` returns a `ready` flag and
the composition holds a bare paper frame until it flips; capture is already
held by `delayRender`, so no frame is ever taken of the empty ground.

Sizes are searched between `headline.max/min` and `beat.max/min` in
`src/theme.ts`, both as fractions of the width. Raise `max` to let short copy
grow; raise `min` to stop long copy getting small. The layout is per format —
reel and square have their own band, measure and bounds in `formats`.

## Fonts

Not stored here. `apps/api/app/assets/fonts` is mounted read-only at
`public/fonts`, so the image renderer and the video renderer read one set of
files and cannot drift. For `remotion studio` on your own machine, copy them
in first:

    .\tf.ps1 studio          # copies the faces, then opens the studio

`src/fonts.ts` loads them explicitly and holds the render until they are
ready. Remotion captures frames as fast as Chromium can paint them, so a face
still being fetched at frame 0 produces a reel whose first second is set in a
fallback — the kind of bug that survives review because it only shows at the
very start.

## Audio

These render **silent**. The voiceover and the music bed are mixed in by
ffmpeg on the Python side, because the voiceover is what decides how long the
reel is: narrate first, measure, then render exactly that many frames.

## Files

| File                      | What it decides                                   |
| ------------------------- | ------------------------------------------------- |
| `src/theme.ts`            | Palette, per-format layout, motion budget         |
| `src/typography.ts`       | Measured line fitting                             |
| `src/texture.ts`          | The paper grain tile                              |
| `src/props.ts`            | The contract with Python, and its defaults        |
| `src/compositions/Wire.tsx` | Chrome, cards, and the order they stack in      |
| `src/components/Reveal.tsx` | The enter/exit move and the rule wipe           |
| `src/components/Ticker.tsx` | The segmented edition line                      |
| `src/components/Sparkline.tsx` | The velocity chart, small and large          |

## What a render costs

Measured on an 8-core, 8GB host, for the 12-second sample reel at 1080x1920:

| Configuration                               | Time | Size   |
| ------------------------------------------- | ---- | ------ |
| Flat paper, no grain, no measured type       | 47s  | 526 KB |
| Current composition                          | 132s | 1.3 MB |
| …with `will-change` on every animated line   | 220s | 1.4 MB |
| …with four Chromium instances instead of two | 195s | 1.0 MB |

Three things worth knowing from that:

- **`will-change` is a pessimisation here.** It promotes every animated line
  to its own compositor layer, which is right for an interactive page and
  wrong for an offline render where nothing is interactive. It cost 88
  seconds.
- **The text fit must be memoised.** It cannot change within a card, so
  without a memo the search runs on all 360 frames for the same answer.
- **More concurrency is not faster.** Four browsers at 1080x1920 contend for
  memory on an 8GB box and finish later than two. `REMOTION_CONCURRENCY`
  stays at 2 unless the host has the RAM for more.

Roughly 11 seconds of render per second of video, which is what
`RENDERER_TIMEOUT_SECONDS` is set against.

## Working on the compositions

    .\tf.ps1 studio          # http://localhost:3101, hot reload
    .\tf.ps1 renderer        # rebuild and restart the container

`src/` and `server/` are bind-mounted into the container, so a design change
needs a restart but not an image rebuild. The image only has to be rebuilt
when a dependency or the Dockerfile changes.
