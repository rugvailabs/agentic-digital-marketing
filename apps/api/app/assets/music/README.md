# Music beds

Empty on purpose. Licensed music is not something this repository can carry,
and a bed is optional by design: a reel with a clear voice and no music is
fine, a reel with music over the voice is not.

Drop royalty-free tracks in here and they are picked up on the next render —
`.mp3`, `.m4a`, `.ogg`, `.wav` or `.flac`. Set `MUSIC_ENABLED=false` to ignore
them without moving the files.

## What happens to a track

- Looped to the length of the reel, so a thirty-second loop covers a
  forty-second reel without a gap.
- Cut to `MUSIC_GAIN_DB` (-18 dB by default).
- Ducked under the narration by a sidechain compressor keyed on the voice. The
  flat gain alone is not enough — a bed that sits politely under one sentence
  will fight the next quieter one.
- Faded in and out over `MUSIC_FADE_SECONDS`.

Which track a reel gets is decided by hashing the job, not at random, so
re-rendering the same reel twice gives the same result. A render that changes
its soundtrack every run is impossible to review.

## Licensing

Whatever you put here ships inside every reel the app renders, so it needs a
licence that covers commercial social use and redistribution. Keep the licence
or the purchase record next to the file.
