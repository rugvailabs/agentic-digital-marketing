# TrendForge — agentic trend marketing for India

## What this is
A web app that ingests what's trending across India and every state, ranks topics with
hashtags, and generates ready-to-post social content (captions, images, short videos) for
each topic using AI agents. Users are small marketing teams and agencies in India.

## Stack (do not substitute without asking)
- Monorepo: pnpm workspaces + Turborepo
- apps/web: Next.js 15 App Router, TypeScript strict, Tailwind v4, no component kit
  (build our own primitives; shadcn only for Dialog/Popover/Toast if needed)
- apps/api: FastAPI, Python 3.12, SQLAlchemy 2 async, Alembic, Pydantic v2, uv for deps
- apps/worker: Celery + Celery Beat (Redis broker). Same Python package as api.
- packages/remotion: Remotion video templates (Reel 9:16, Square 1:1)
- packages/types: TS types generated from the FastAPI OpenAPI schema
- DB: Postgres 16 + pgvector (Supabase in prod, docker locally)
- Cache/queue: Redis (Upstash in prod)
- Storage: S3-compatible (Cloudflare R2); MinIO locally
- LLM: Gemini via google-genai SDK, behind an LLMProvider interface
- Images: templated rendering with Pillow (default); optional Gemini image backgrounds
- Video: Remotion render + FFmpeg; TTS via edge-tts; music from local royalty-free pack
- Trends: Google Trends (trendspy), Google News RSS, YouTube Data API, X API (optional)
- Auth: Clerk. Observability: Sentry; log every LLM call with prompt id, tokens, latency.

## Architecture rules
- Every external capability is an adapter behind an interface:
  TrendSource, LLMProvider, ImageProvider, VideoProvider, TTSProvider, Publisher.
  Each exposes is_configured(); unconfigured adapters are skipped, never crash.
- Agent pipeline = idempotent Celery tasks with explicit status on the row:
  ingest -> curate -> plan -> write -> render_image -> render_video -> review -> publish.
- Prompts live in apps/api/app/prompts/*.md with a version in the filename. Never inline.
- Hashtag and text normalisation lives only in app/core/hashtags.py; never write a
  \w-based regex for Indic text anywhere else. Python's `\w` and `str.isalnum()` are
  False for combining marks — Devanagari matras, Tamil vowel signs, nuktas, viramas are
  Mn/Mc/Me, not letters — so such a pattern silently returns a different word: मौसम
  becomes मसम, मझै becomes मझ. It has shipped four times here (normalise_topic, the
  voiceover's _speakable, the Reddit literal-tag regex, the hashtag grounding filter)
  and each time passed its tests, because the tests were ASCII. Any text-handling
  change needs a Hindi and a Tamil case.
- Region model: country > state > city. X WOEIDs attach to cities and roll up to states.
- Safety: the planner skips trends tagged disaster/death/communal/election-result;
  content about real named people is descriptive only, never endorsements.
- Indian context everywhere: INR, IST, en-IN dates, Hinglish and Indic scripts must render
  (bundle Noto Sans Devanagari/Tamil/Telugu/Bengali/Gujarati/Kannada/Malayalam for Pillow
  and Remotion).

## Design system — read before touching UI
The UI must not look like a generic AI-generated dashboard. Specifically avoid:
cream background + serif + terracotta; black + neon green; identical rounded cards with
grey shadows; all-caps tracked eyebrow labels; "01/02/03" numbering where nothing is a
sequence; gradient blobs; middle-dot meta strings; arrows appended to buttons; Inter;
stat tiles across the top; icons or emoji next to every label; centered hero text.
Lucide is the only icon set, and it appears on nav items and on buttons that do
something — never beside a field label or a heading.

Direction: a newsroom wire desk for marketers. Dense, confident, Indian, fast to scan.

### Tokens
Everything lives in `apps/web/src/app/globals.css`, in one `@theme` block. Dark is the
default and holds the base values; `:root[data-theme='light']` overrides them. There is
no `prefers-color-scheme` branch — light is a choice the user makes and we remember.
**No component may branch on theme.** A component names a surface; the surface knows
what it looks like.

- Surfaces, in stacking order: `page` (the ground) / `panel` (a region — sidebar, Desk,
  a section) / `card` (a discrete object you can act on) / `overlay` (dialog, popover).
  In dark each step is one shade lighter than the one below. In light all three upper
  steps are near-white and the step is carried by shadow, because four distinguishable
  near-whites do not exist. The ladder keeps `row-hover` / `row-active` so a selected
  row still reads as a row and not as a card.
- Lines: `border` is the resting hairline, `border-hover` the same line brightened —
  that brightening is how a thing says it is interactive before you click it. `rule` is
  the quieter dotted wire-feed line between ladder rows.
- Ink: `ink` (read this) / `slate` (secondary) / `muted` (present but not being read —
  timestamps, units, disabled labels).
- Accent: still one. `chilli` means rising velocity and marks the focused control, and
  nothing else may claim it. `neem` is falling, `turmeric` is watch (topics the curator
  flags as sensitive). Signals, never decoration.
- Heat ramp: `heat-0`..`heat-4`, five steps of the one accent, for the dashboard
  choropleth. The direction flips between themes — dark recedes on the dark page, pale
  recedes on the light one — which is exactly why it is tokens and not a function in the
  component.
- Radius: `sm` 4px (controls) / `md` 6px (cards) / `lg` 10px (panels). The ladder stays
  square: a rounded wire feed is a list of pills.
- Depth: `shadow-card` / `shadow-lift` / `shadow-overlay`, redefined per theme, because a
  shadow in dark is a darker black and in light is a soft grey.
- Layout: `topbar` 56px, `sidebar` 240px, `sidebar-rail` 56px, `wire` 400px, `desk` 760px
  max measure. The `desk` breakpoint is 900px — note Tailwind v4 orders variants by
  width, so `lg:` (1024) wins over `desk:` above 1024 and the two must not be mixed on
  one property.

### Control states
Written down once in `apps/web/src/components/ui.tsx`, not re-decided per file. Five
states for everything: **rest**; **hover**, where the border brightens — the house signal
for "this is interactive", and the only one that reads equally well in both themes;
**active**, which moves a pixel toward you so a click feels like a click; **focus**, the
2px chilli ring, never overridden; **disabled**, 40% opacity and `not-allowed`, never a
different colour — a greyed control in a different grey from the text around it reads as
a bug. Cards additionally lift 4px with `shadow-lift` on hover. All of it is 150ms on
`--ease-out-quick`; longer reads as lag on a pointer.

### Shell
Fixed 56px top bar: app name, global search (⌘K), IST clock, pipeline health dot. A
240px left sidebar — Dashboard, Board, Library, Calendar, Brands, Settings, with the
theme toggle, the collapse toggle and the workspace at the bottom. It collapses to a
56px icon rail; both the theme and the rail are written to `data-theme` / `data-sidebar`
by an inline head script before first paint, so neither flashes. Sidebar labels stay in
the DOM when railed and are hidden by CSS, so the accessible name survives the toggle.
Below the `desk` breakpoint the sidebar becomes a bottom nav and the Desk becomes a
slide-in panel.

### Pages
- **Dashboard**: an SVG choropleth of India coloured by today's trend heat (rising share,
  quantile buckets — a linear ramp paints the whole country red), clickable through to
  the board; top 5 movers; posts and reels made this week with their posters; budget
  remaining per provider as bars; the next 5 scheduled items; pipeline status. Real data
  only — never a placeholder number.
- **Board**: the ladder is unchanged — left Wire column, region strip on top, ranked rows
  separated by a 1px dotted rule, rank numerals hanging slightly outside the text column
  like a newspaper folio. The Desk on the right is a panel with tabs: Overview, Post,
  Reel, Evidence. Generated assets are cards with actions revealed on hover.
- **Library**: a card grid with poster or thumbnail, brand badge and status, actions on
  hover, and a list-view toggle that is remembered.
- **Brands**: cards showing the colour swatches, the logo and the three templates at
  thumbnail size — a brand is a look, so show the look. The editor is two columns with a
  sticky preview.
- **Calendar**: items as cards with poster thumbnails, today highlighted, caption preview
  on hover.

### Numbers, motion, loading
- Numbers are the star: rank numerals are 64px Bricolage (48px from rank 4 down).
- Velocity is a 6-point SVG sparkline beside each topic.
- Motion: one load-in for the ladder (rows settle top to bottom, 240ms total), and motion
  that answers an action — a row expanding, a card lifting, a render completing. Nothing
  else. Respect `prefers-reduced-motion`.
- Type: Bricolage Grotesque for display and numerals (500/700/800, optical size),
  Schibsted Grotesk for body and UI (400/500/600). Scale 12/14/16/20/28/40, plus 48/64
  for ranks.
- Every route that loads data has a `loading.tsx` with a skeleton **shaped like what is
  arriving**, so the layout does not jump. One `role="status"` live region per group:
  a screen reader hears "loading", not forty empty boxes.
- Every empty state uses `EmptyState` from `components/Empty.tsx` with one of the SVG
  illustrations drawn there — `currentColor` plus a single chilli stroke, made of the
  same shapes the real surface is made of — and says what to do next. No illustration
  dependency, nothing decorative.

### Copy and accessibility
Sentence case, plain verbs. Buttons say what happens: "Generate post", "Render reel",
"Schedule". No "Welcome back", no "Insights". Visible focus rings (2px chilli), 4.5:1
contrast in both themes, the ladder is keyboard-navigable, every icon has a label.
Indian context everywhere: INR, IST, en-IN dates, and Hinglish and Indic scripts must
render.

## Working conventions
- Small PR-sized steps. After each step: run lint, typecheck, tests; show me screenshots
  of UI changes (use Playwright screenshot in apps/web/scripts/shot.ts).
- Don't add dependencies without saying why in one line.
- .env.example is the source of truth for config; never commit secrets.
- Tests: pytest for api/worker (adapters mocked), Vitest for web, Playwright smoke for
  the main flow.
