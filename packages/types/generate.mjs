/**
 * Generate src/generated/api.ts from the running API's OpenAPI schema.
 *
 *   pnpm --filter @trendforge/types generate
 *   TRENDFORGE_OPENAPI=http://host:port/openapi.json pnpm ... generate
 *
 * A node script rather than `${VAR:-default}` in the npm script: that is shell
 * syntax, and on Windows it reaches openapi-typescript as a literal path.
 */

import { spawnSync } from 'node:child_process'

const url = process.env.TRENDFORGE_OPENAPI ?? 'http://localhost:8020/openapi.json'
const out = 'src/generated/api.ts'

console.log(`[types] ${url} -> ${out}`)
const result = spawnSync('openapi-typescript', [url, '-o', out], {
  stdio: 'inherit',
  shell: true,
})
process.exit(result.status ?? 1)
