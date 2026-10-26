/**
 * The same bundled faces the Pillow templates use.
 *
 * The files are not copied here: the renderer service mounts
 * apps/api/app/assets/fonts read-only at its public/fonts, so both renderers
 * read one set of files and cannot drift. `pnpm --filter @trendforge/remotion
 * fonts` does the same thing locally for `remotion studio`.
 *
 * Loading is explicit rather than left to CSS. Remotion captures frames as
 * fast as Chromium can paint them, so a face still being fetched when frame 0
 * is taken produces a reel whose first second is set in a fallback — exactly
 * the kind of bug that survives review, because it only shows at the very
 * start.
 */

import { useEffect, useState } from 'react'
import { continueRender, delayRender, staticFile } from 'remotion'

/** Unicode script name -> bundled face, matching app/images/fonts.py. */
const SCRIPT_FILES: Record<string, string> = {
  DEVANAGARI: 'NotoSansDevanagari.ttf',
  TAMIL: 'NotoSansTamil.ttf',
  TELUGU: 'NotoSansTelugu.ttf',
  BENGALI: 'NotoSansBengali.ttf',
  GUJARATI: 'NotoSansGujarati.ttf',
  KANNADA: 'NotoSansKannada.ttf',
  MALAYALAM: 'NotoSansMalayalam.ttf',
}

const DISPLAY_FILE = 'BricolageGrotesque.ttf'
const UI_FILE = 'SchibstedGrotesk.ttf'

/**
 * The weight range each file actually carries.
 *
 * Not optional. A FontFace registered without a `weight` descriptor defaults
 * to `normal`, and the browser then treats a variable font as one static
 * weight: `font-weight: 800` matches the face but changes nothing, so every
 * headline in the reel came out at Regular. It also makes the measurement
 * wrong, because the text is measured at a weight it will not be set in.
 */
const WEIGHTS: Record<string, string> = {
  [DISPLAY_FILE]: '200 800',
  [UI_FILE]: '400 900',
}
const INDIC_WEIGHTS = '100 900'

export const DISPLAY_FAMILY = 'TrendForge Display'
export const UI_FAMILY = 'TrendForge UI'
export const SCRIPT_FAMILY = 'TrendForge Script'

export type Families = {
  display: string
  ui: string
  /**
   * False until the faces are in `document.fonts`.
   *
   * Text is measured to decide its size, and measuring against a fallback
   * face gives the wrong answer — the layout would be built for a font that
   * is not the one it renders in. Callers hold off drawing until this flips.
   * Capture is already held by delayRender, so no frame is ever taken while
   * it is false.
   */
  ready: boolean
  /**
   * True when the script is set in a Noto Indic face.
   *
   * Indic glyphs are taller than Latin ones — Tamil and Devanagari carry
   * marks above and below the base character — so a leading that looks tight
   * and confident in Bricolage has the lines colliding in Tamil.
   */
  indic: boolean
}

function filesFor(script: string): { family: string; file: string }[] {
  const indic = SCRIPT_FILES[script]
  return [
    { family: DISPLAY_FAMILY, file: DISPLAY_FILE },
    { family: UI_FAMILY, file: UI_FILE },
    // Only the script in play. Loading all seven would mean several megabytes
    // of fonts parsed before the first frame of a reel that uses one of them.
    ...(indic ? [{ family: SCRIPT_FAMILY, file: indic }] : []),
  ]
}

/**
 * Load the faces this reel needs, holding the render until they are ready.
 *
 * Returns the families to set type in. An Indic script uses its Noto face for
 * everything: neither Latin face has a Devanagari or Tamil glyph, and a
 * missing glyph is a blank box rather than a graceful fallback.
 */
export function useFonts(script: string): Families {
  const indic = Boolean(SCRIPT_FILES[script])
  const [handle] = useState(() => delayRender(`fonts:${script}`))
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    void Promise.all(
      filesFor(script).map(async ({ family, file }) => {
        const face = new FontFace(family, `url(${staticFile(`fonts/${file}`)})`, {
          weight: WEIGHTS[file] ?? INDIC_WEIGHTS,
        })
        await face.load()
        document.fonts.add(face)
      }),
    )
      .catch((error: unknown) => {
        // Continue anyway: a reel set in the fallback face is worth more than
        // no reel, and the message names the cause in the renderer's log.
        // eslint-disable-next-line no-console
        console.error(`[remotion] font load failed for ${script}:`, error)
      })
      .finally(() => {
        if (cancelled) return
        // Ready before continueRender: the measured layout has to exist in
        // the tree before the frame is allowed to be captured.
        setReady(true)
        continueRender(handle)
      })

    return () => {
      cancelled = true
      continueRender(handle)
    }
  }, [handle, script])

  return indic
    ? { display: SCRIPT_FAMILY, ui: SCRIPT_FAMILY, ready, indic }
    : { display: DISPLAY_FAMILY, ui: UI_FAMILY, ready, indic }
}
