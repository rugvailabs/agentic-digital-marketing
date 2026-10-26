/**
 * Copy the bundled faces into public/fonts for `remotion studio`.
 *
 * The renderer service mounts apps/api/app/assets/fonts read-only instead, so
 * this is only for working on the compositions by hand. public/fonts is
 * gitignored: one copy of these files in the repo is enough.
 */

import { cp, mkdir, readdir } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const source = resolve(here, '..', '..', '..', 'apps', 'api', 'app', 'assets', 'fonts')
const target = resolve(here, '..', 'public', 'fonts')

await mkdir(target, { recursive: true })
const files = (await readdir(source)).filter((f) => f.endsWith('.ttf'))
for (const file of files) {
  await cp(join(source, file), join(target, file))
}
console.log(`[remotion] ${files.length} faces -> public/fonts`)
