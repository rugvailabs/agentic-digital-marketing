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

Direction: a newsroom wire desk for marketers. Dense, confident, Indian, fast to scan.
- Palette: paper #EEF1F6, ink #1B2230, slate #5B6578 (secondary text; flat /
  settled velocity), rule #D5DAE3, chilli #D8322B (rising velocity, and the
  focus ring below — nothing else), neem #1E7D5A (falling velocity),
  turmeric #E3A51D (watch — held for topics the curator flags as sensitive,
  from step 2; nothing else may claim it meanwhile),
  surface #FFFFFF. Dark mode mirrors with paper #121722, surface #1A2130, ink #EDF0F5.
- Type: Bricolage Grotesque for display and numerals (weights 500/700/800, use optical
  size), Schibsted Grotesk for body/UI (400/500/600). Scale: 12/14/16/20/28/40/64.
  Numbers are the star: rank numerals are 64px Bricolage, hanging slightly outside the
  text column like a newspaper folio.
- Layout: left "Wire" column (region strip on top, ranked topic ladder below) and a wide
  "Desk" area on the right (selected topic -> content studio). Fixed 56px top bar with
  app name, IST clock, and the pipeline health dot. Left-aligned everywhere.
- Hierarchy is carried by type size, weight and the single chilli accent — not by boxes.
  Use rules and spacing to group; ladder rows are separated by a 1px dotted rule (wire
  feed feel). Cards only for generated assets (image/video previews).
- Velocity is shown as a tiny 6-point sparkline next to each topic, drawn with SVG.
- Motion: one load-in for the ladder (rows settle top to bottom, 240ms total), and
  motion that answers actions (a row expanding, a render completing). Nothing else.
  Respect prefers-reduced-motion.
- Copy: sentence case, plain verbs. Buttons say what happens: "Generate post",
  "Render reel", "Schedule". Empty states tell the user what to do next. No "Welcome
  back", no "Insights".
- Accessibility: visible focus rings (2px chilli), 4.5:1 contrast, keyboard-navigable
  ladder, every icon has a label.

## Working conventions
- Small PR-sized steps. After each step: run lint, typecheck, tests; show me screenshots
  of UI changes (use Playwright screenshot in apps/web/scripts/shot.ts).
- Don't add dependencies without saying why in one line.
- .env.example is the source of truth for config; never commit secrets.
- Tests: pytest for api/worker (adapters mocked), Vitest for web, Playwright smoke for
  the main flow.
