import Link from 'next/link'

import { Code, SectionLabel } from '@/components/primitives'
import { fetchPlatforms } from '@/lib/api'

/**
 * Rendered per request, not at build time.
 *
 * Next prerenders a page with no dynamic inputs, and these all read the
 * API — so a build would either bake in whatever the board said that
 * afternoon or, with no API reachable, fail outright. Which is what it did.
 */
export const dynamic = 'force-dynamic'

export const metadata = { title: 'Platforms — TrendForge' }

/**
 * What is connected, and what to set to connect the rest.
 *
 * A read-only page on purpose. The keys live in `.env`, which is the source of
 * truth per CLAUDE.md, and a form here would either write to a file the
 * running container has already read or keep a second copy of each secret in
 * the database. Naming the variable is the useful half; pasting it is a text
 * editor's job.
 *
 * Names come from the API's `label`, not the short SOURCE_LABELS the ladder
 * uses: there is room here, and "Google Trends" is what a user is looking for
 * in their own notes, not "Trends".
 */
export default async function SettingsPage() {
  const platforms = await fetchPlatforms()
  const connected = platforms.filter((p) => p.configured)
  const missing = platforms.filter((p) => !p.configured)

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/" className="text-sm text-slate hover:text-ink">
        Back to the board
      </Link>

      <h1 className="mt-6 font-display text-[28px] leading-tight font-bold text-ink">
        Trend platforms
      </h1>
      <p className="mt-2 max-w-prose text-sm text-slate">
        Each platform is read by its own adapter. One without credentials is skipped, never fatal —
        the board keeps working on whatever else answered.
      </p>

      {missing.length > 0 ? (
        <section className="mt-8">
          <SectionLabel>Not connected</SectionLabel>
          <ul className="mt-3">
            {missing.map((platform) => (
              <li
                key={platform.name}
                className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-dotted border-rule py-3"
              >
                <span className="text-base text-ink">{platform.label || platform.name}</span>
                <span className="flex flex-wrap gap-2">
                  {platform.env_vars.map((name) => (
                    <Code key={name}>{name}</Code>
                  ))}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 max-w-prose text-sm text-slate">
            Set these in <Code>.env</Code>, then recreate the stack with <Code>.\tf.ps1 up</Code>. A
            restart is not enough: the containers read their environment once, at startup.
          </p>
        </section>
      ) : null}

      <section className="mt-10">
        <SectionLabel>Connected</SectionLabel>
        {connected.length === 0 ? (
          <p className="mt-3 text-sm text-slate">
            Nothing is connected. Google Trends and Google News need no credentials, so this usually
            means the API is unreachable.
          </p>
        ) : (
          <ul className="mt-3">
            {connected.map((platform) => (
              <li
                key={platform.name}
                className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-dotted border-rule py-3"
              >
                <span className="text-base text-ink">{platform.label || platform.name}</span>
                <span className="text-sm text-slate">
                  {platform.env_vars.length === 0
                    ? 'no credentials needed'
                    : `set via ${platform.env_vars.join(', ')}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
