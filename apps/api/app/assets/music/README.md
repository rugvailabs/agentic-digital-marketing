# Music beds

Three tracks ship here; `LICENSE.txt` records where each came from and under
what licence. **Add a block there when you add a track** — these files are
mixed into every reel the app renders and distributes, so the licence is not
paperwork, it is the thing that makes shipping them legal.

A bed stays optional by design: a reel with a clear voice and no music is
fine, a reel with music over the voice is not. Empty the directory and reels
go out voice-only.

Drop royalty-free tracks in here and they are picked up on the next render —
`.mp3`, `.m4a`, `.ogg`, `.wav` or `.flac`. Set `MUSIC_ENABLED=false` to ignore
them without moving the files.

## What happens to a track

- Looped to the length of the reel, so a thirty-second loop covers a
  forty-second reel without a gap.
- Cut to `MUSIC_GAIN_DB` (-12 dB by default).
- Ducked under the narration by a sidechain compressor keyed on the voice. The
  flat gain alone is not enough — a bed that sits politely under one sentence
  will fight the next quieter one.
- Faded in and out over `MUSIC_FADE_SECONDS`.

Which track a reel gets is decided by hashing the job, not at random, so
re-rendering the same reel twice gives the same result. A render that changes
its soundtrack every run is impossible to review.

## Levels, measured

Numbers rather than taste, against `zephiramusic-lo-fi-581502.mp3` under a
real en-IN narration:

| Signal                   | Mean    |
| ------------------------ | ------- |
| Narration                | -21.6 dBFS |
| Bed, gain only           | -34.9 dBFS |
| Bed, gain + sidechain    | -37.7 dBFS |

So the bed sits 13 dB under the voice in the clear and 16 dB under it while
someone is speaking — the compressor accounts for 2.8 dB of that.

Both numbers were wrong at first and the measurement is what found it. At
`-18 dB` the bed landed at -41 dBFS, eighteen under the narration, which is
not a quiet bed but an inaudible one — and with a 12:1 compressor on top it
was not ducked but gated, vanishing under every sentence and jumping back in
the pauses. A bed should be continuously present and continuously
subordinate.

## Licensing

Whatever you put here ships inside every reel the app renders, so it needs a
licence that covers commercial social use and redistribution. Record it in
`LICENSE.txt` next to the file.
