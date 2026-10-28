/**
 * Build src/lib/india-map.ts from Natural Earth.
 *
 *   pnpm --filter @trendforge/web build:map
 *
 * The output is committed, so this only needs running if the boundaries or
 * the simplification change. It is in the repo so the asset is
 * reproducible rather than a blob somebody pasted in once.
 *
 * Source: Natural Earth 1:50m admin-1 states and provinces, which is
 * explicitly public domain ("No permission is needed to use Natural
 * Earth"). 2.3MB for the whole world, so it is downloaded rather than
 * vendored, and India's 36 features are kept.
 *
 * Projection: equidistant cylindrical with a standard parallel at 23°N,
 * roughly India's middle. Web Mercator was tried first and stretches
 * Ladakh and Kashmir badly over a 8°N–37°N span — on a map whose whole job
 * is to let someone pick their state, the north being wrong is the half
 * that matters.
 */

import { writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = resolve(HERE, '..', 'src', 'lib', 'india-map.ts')

const SOURCE =
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_1_states_provinces.geojson'

/** The viewBox the paths are projected into. */
const WIDTH = 1000
const HEIGHT = 1100

/**
 * Douglas-Peucker tolerance, in projected units.
 *
 * 0.9 keeps every coastline and border legible at the ~520px the dashboard
 * draws this at, and takes the file from 1.6MB to about 50KB. Below 0.5
 * the file doubles for detail nobody can see; above 1.5 Goa stops being
 * Goa.
 */
const TOLERANCE = 0.9

/** Natural Earth still carries Orissa's pre-2011 code. */
const CODE_ALIASES: Record<string, string> = { 'IN-OR': 'IN-OD' }

type Ring = Array<[number, number]>
type Feature = {
  properties: { admin?: string; name?: string; iso_3166_2?: string }
  geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: unknown }
}

const RAD = Math.PI / 180
const STANDARD_PARALLEL = 23 * RAD

function project([lon, lat]: [number, number]): [number, number] {
  return [lon * Math.cos(STANDARD_PARALLEL), -lat]
}

/** Perpendicular distance from `p` to the segment `a`–`b`. */
function distance(p: [number, number], a: [number, number], b: [number, number]): number {
  const [px, py] = p
  const [ax, ay] = a
  const [bx, by] = b
  const dx = bx - ax
  const dy = by - ay
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay)
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy))
}

/** Douglas-Peucker, iteratively — a recursive one blows the stack on a
 *  coastline with 40,000 points. */
function simplify(points: Ring, tolerance: number): Ring {
  if (points.length < 3) return points
  const keep = new Array<boolean>(points.length).fill(false)
  keep[0] = true
  keep[points.length - 1] = true

  const stack: Array<[number, number]> = [[0, points.length - 1]]
  while (stack.length > 0) {
    const [first, last] = stack.pop()!
    let worst = 0
    let index = -1
    for (let i = first + 1; i < last; i++) {
      const d = distance(points[i]!, points[first]!, points[last]!)
      if (d > worst) {
        worst = d
        index = i
      }
    }
    if (worst > tolerance && index > 0) {
      keep[index] = true
      stack.push([first, index], [index, last])
    }
  }

  return points.filter((_, i) => keep[i])
}

function ringsOf(feature: Feature): Ring[] {
  const { type, coordinates } = feature.geometry
  const polygons = (type === 'Polygon' ? [coordinates] : (coordinates as unknown[])) as Array<
    Array<Ring>
  >
  // Outer ring only. Holes exist in this dataset (lakes, enclaves) and at
  // 0.9 tolerance they are mostly a pixel or two — not worth doubling the
  // path data to draw.
  return polygons.map((polygon) => polygon[0]!).filter((ring) => ring && ring.length > 2)
}

async function main(): Promise<void> {
  console.log(`[map] ${SOURCE}`)
  const response = await fetch(SOURCE)
  if (!response.ok) throw new Error(`source returned ${response.status}`)
  const data = (await response.json()) as { features: Feature[] }

  const india = data.features.filter((f) => f.properties.admin === 'India')
  if (india.length === 0) throw new Error('no Indian features — did the source change shape?')
  console.log(`[map] ${india.length} features`)

  // Every ring, projected, so the extent is measured once over all of them
  // and each state lands in the same coordinate space.
  const states = india.map((feature) => ({
    code: CODE_ALIASES[feature.properties.iso_3166_2 ?? ''] ?? feature.properties.iso_3166_2 ?? '',
    name: feature.properties.name ?? '',
    rings: ringsOf(feature).map((ring) => ring.map(project)),
  }))

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const state of states) {
    for (const ring of state.rings) {
      for (const [x, y] of ring) {
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      }
    }
  }

  // One scale for both axes, or the country is stretched.
  const scale = Math.min(WIDTH / (maxX - minX), HEIGHT / (maxY - minY))
  const offsetX = (WIDTH - (maxX - minX) * scale) / 2
  const offsetY = (HEIGHT - (maxY - minY) * scale) / 2

  const entries = states
    .map((state) => {
      const d = state.rings
        .map((ring) =>
          simplify(
            ring.map(([x, y]) => [(x - minX) * scale + offsetX, (y - minY) * scale + offsetY]),
            TOLERANCE,
          ),
        )
        // A ring that simplifies to a triangle is a sandbank, not a state.
        .filter((ring) => ring.length >= 4)
        .map((ring) => `M${ring.map(([x, y]) => `${round(x)} ${round(y)}`).join('L')}Z`)
        .join('')
      return { ...state, d }
    })
    .filter((state) => state.code && state.d)
    .sort((a, b) => a.code.localeCompare(b.code))

  const file = `/**
 * India's states and union territories as SVG paths.
 *
 * GENERATED — do not edit. Run \`pnpm --filter @trendforge/web build:map\`.
 *
 * Source: Natural Earth 1:50m admin-1, public domain. Projected
 * equidistant-cylindrical at a 23°N standard parallel and simplified with
 * Douglas-Peucker; see scripts/build-india-map.ts for why those two.
 *
 * Codes are ISO 3166-2 and match the \`regions\` table, so a path can be
 * joined straight onto a region without a lookup table.
 */

export const INDIA_VIEWBOX = '0 0 ${WIDTH} ${HEIGHT}'

export type MapState = {
  /** ISO 3166-2, e.g. "IN-TN". The same code the regions table uses. */
  code: string
  name: string
  /** The outer rings, as one path. */
  d: string
}

export const INDIA_STATES: MapState[] = [
${entries
  .map(
    (s) =>
      `  { code: ${JSON.stringify(s.code)}, name: ${JSON.stringify(s.name)}, d: ${JSON.stringify(s.d)} },`,
  )
  .join('\n')}
]
`

  await writeFile(OUT, file, 'utf8')
  const kb = Math.round(file.length / 1024)
  console.log(`[map] ${entries.length} states -> ${OUT} (${kb}KB)`)
}

function round(n: number): string {
  // One decimal. At a 1000-unit viewBox drawn around 520px, a tenth of a
  // unit is a twentieth of a pixel.
  return (Math.round(n * 10) / 10).toString()
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error)
  process.exit(1)
})
