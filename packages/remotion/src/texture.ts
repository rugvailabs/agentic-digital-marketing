/**
 * Paper grain.
 *
 * A flat #EEF1F6 field at 1080px reads as a screenshot of a text editor. A
 * little tooth makes it read as stock, which is the point of calling the
 * colour "paper" — and it survives the compression every social platform puts
 * a reel through, where a perfectly flat field is where banding shows first.
 *
 * Three decisions here are all about what it costs:
 *
 * 1. A tiled SVG, not a full-screen `feTurbulence` filter. The tile is
 *    rasterised once and repeated by the compositor; the filter would be
 *    re-evaluated on every one of 360 frames.
 * 2. The alpha is baked into the SVG, so this is a background-image on the
 *    root rather than a layer above the cards. A separate layer with
 *    `mix-blend-mode: multiply` put the grain over the type as well, and cost
 *    six times the render — 292s against 47s for the same reel, because the
 *    compositor had to blend the full canvas every frame.
 * 3. Low contrast and a coarse frequency. Noise is the enemy of an inter-frame
 *    codec: the first version tripled the file size, because h264 cannot
 *    predict grain from the previous frame and spends real bits on it.
 *
 * Fixed seed, so every frame gets the same grain and the texture does not
 * crawl.
 */

const TILE = 160
/** Coarser than it looks right at 1:1, and deliberately so: fine grain is
 *  expensive to encode and disappears on a phone anyway. */
const FREQUENCY = 0.65
/** Felt rather than seen. Above about 0.09 it stops being paper. */
const ALPHA = 0.07

const svg = [
  `<svg xmlns='http://www.w3.org/2000/svg' width='${TILE}' height='${TILE}'>`,
  `<filter id='g'>`,
  `<feTurbulence type='fractalNoise' baseFrequency='${FREQUENCY}'`,
  ` numOctaves='2' stitchTiles='stitch' seed='7'/>`,
  `</filter>`,
  `<rect width='${TILE}' height='${TILE}' filter='url(%23g)' opacity='${ALPHA}'/>`,
  `</svg>`,
].join('')

export const grainUrl = `url("data:image/svg+xml,${svg.replace(/"/g, "'")}")`
