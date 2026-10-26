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

## Working on the compositions

    .\tf.ps1 studio          # http://localhost:3101, hot reload
    .\tf.ps1 renderer        # rebuild and restart the container

`src/` and `server/` are bind-mounted into the container, so a design change
needs a restart but not an image rebuild. The image only has to be rebuilt
when a dependency or the Dockerfile changes.
