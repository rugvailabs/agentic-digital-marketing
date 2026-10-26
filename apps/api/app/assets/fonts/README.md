# Bundled typefaces

Bundled rather than fetched at render time: a post or a reel must render the
same way on a laptop, in CI and in the worker, and a font CDN is one more thing
that can be down when a marketer presses "Generate post".

All of these are variable fonts, so one file covers every weight the templates
ask for. Every face here is licensed under the SIL Open Font License v1.1 —
see `OFL.txt`, which applies to all of them.

| File                       | Family              | Used for                                     |
| -------------------------- | ------------------- | -------------------------------------------- |
| `BricolageGrotesque.ttf`   | Bricolage Grotesque | Latin display type and numerals (`opsz` set) |
| `SchibstedGrotesk.ttf`     | Schibsted Grotesk   | Latin body and UI type                       |
| `NotoSans.ttf`             | Noto Sans           | Latin fallback, and any script not below     |
| `NotoSansDevanagari.ttf`   | Noto Sans Devanagari| Hindi, Marathi                               |
| `NotoSansTamil.ttf`        | Noto Sans Tamil     | Tamil                                        |
| `NotoSansTelugu.ttf`       | Noto Sans Telugu    | Telugu                                       |
| `NotoSansBengali.ttf`      | Noto Sans Bengali   | Bengali                                      |
| `NotoSansGujarati.ttf`     | Noto Sans Gujarati  | Gujarati                                     |
| `NotoSansKannada.ttf`      | Noto Sans Kannada   | Kannada                                      |
| `NotoSansMalayalam.ttf`    | Noto Sans Malayalam | Malayalam                                    |

Sources: [Bricolage Grotesque](https://github.com/ateliertriay/bricolage),
[Schibsted Grotesk](https://github.com/schibsted/schibsted-grotesk),
[Noto](https://github.com/notofonts) — all via
[google/fonts](https://github.com/google/fonts).

## Why there is no Bricolage for Indic scripts

Bricolage and Schibsted cover Latin (and Schibsted some Cyrillic); neither has
Devanagari or any South Indian script. A Hindi headline therefore sets in Noto
Sans Devanagari while its English brand line sets in Schibsted, which is the
correct outcome: matching the Latin face is not worth setting Devanagari in a
font that has no Devanagari.

## Who reads these

- `apps/api/app/images/fonts.py` — Pillow, for post images.
- `packages/remotion/src/fonts.ts` — Remotion, for reels. The renderer service
  mounts this directory read-only at its `public/fonts`, so both renderers use
  the same files rather than two copies that can drift.
