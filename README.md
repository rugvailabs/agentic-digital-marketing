# TrendForge

Agentic trend marketing for India. **Step 1: foundation + a real trend board
from free data sources.** No AI content generation yet — that's step 2.

What works today: trends are ingested every 30 minutes from Google Trends,
Google News RSS and (optionally) YouTube for India and all 36 states/UTs,
merged and scored without any LLM, and shown on a Wire + Desk board.

---

## Prerequisites

| Tool            | Version          | Notes                                            |
| --------------- | ---------------- | ------------------------------------------------ |
| Docker Desktop  | any recent       | **Linux containers** mode, must be running       |
| Node            | ≥ 20.11 (22 LTS) | for the web app on the host                      |
| pnpm            | 9.x              | `npm install -g pnpm@9.15.4`                     |
| Python on host  | not required     | api/worker run in Docker; `uv` lives in the image |

`make` is not assumed — on Windows use `.\tf.ps1 <target>`, which mirrors every
Makefile target one-for-one.

---

## Start everything on Windows

Open **PowerShell** in the repo root:

```powershell
# 0. one-time: config + JS deps
Copy-Item .env.example .env
npm install -g pnpm@9.15.4
pnpm install

# 1. infra + api + worker + beat, then migrate + seed the 37 regions
.\tf.ps1 up

# 2. pull real trends once (don't wait for the 30-minute beat)
.\tf.ps1 ingest

# 3. the board, on the host, with hot reload
.\tf.ps1 dev
```

Then open <http://localhost:3020>.

Ports are deliberately off the usual defaults (5432/6379/9000/8000/3000 are
commonly already taken on a dev box); change them in `.env` if you like.

| Surface        | URL                                      |
| -------------- | ---------------------------------------- |
| Board (web)    | http://localhost:3020                    |
| API health     | http://localhost:8020/health             |
| API docs       | http://localhost:8020/docs               |
| MinIO console  | http://localhost:9021 (trendforge / trendforge-secret) |
| Postgres       | localhost:5452 (trendforge / trendforge) |

Shut down with `.\tf.ps1 down` (volumes kept) or `.\tf.ps1 reset-db` to wipe
and rebuild the database.

### Why the split

`api`, `worker` and `beat` run in containers; `web` runs on the host. Celery has
no supported Windows worker pool, and Next.js HMR is much faster outside a
bind-mounted container. If you want the web app containerised too:

```powershell
docker compose --profile web up web
```

---

## Everyday commands

```powershell
.\tf.ps1 help        # list every target
.\tf.ps1 logs        # tail api + worker + beat
.\tf.ps1 ingest      # one ingest cycle, synchronous
.\tf.ps1 test        # pytest (network mocked) + vitest
.\tf.ps1 lint        # ruff + eslint
.\tf.ps1 typecheck   # mypy + tsc
.\tf.ps1 shots       # Playwright screenshots, light + dark
.\tf.ps1 migrate     # alembic upgrade head
.\tf.ps1 revision -m "add publishers table"
```

On macOS/Linux/WSL the same targets work as `make up`, `make test`, …

---

## Repo layout

```
apps/
  web/        Next.js 15 App Router, Tailwind v4, own primitives  (host)
  api/        FastAPI + SQLAlchemy 2 async + Alembic + adapters    (docker)
  worker/     docs only — Celery runs the apps/api package         (docker)
packages/
  types/      TS types generated from the API's OpenAPI schema
  remotion/   placeholder for step 3 video templates
```

`apps/api` and `apps/worker` are deliberately **outside** the pnpm workspace —
they're Python. Python tasks go through the task runner, not through Turborepo.

---

## Data sources

| Source             | Credential        | Status in step 1                        |
| ------------------ | ----------------- | --------------------------------------- |
| Google Trends      | none              | on, via `trendspy`                      |
| Google News RSS    | none              | on, en-IN national + per-state queries  |
| YouTube Data v3    | `YOUTUBE_API_KEY` | **off until you set the key** in `.env` |
| X / Twitter        | `X_BEARER_TOKEN`  | stub — implements the interface, returns `[]` |

Every adapter implements `TrendSource.is_configured()`; an unconfigured source
is skipped with a log line and never breaks a run. So the board fills with real
data on a clean checkout with no keys at all.

---

## Next

Step 2 adds the content studio: the agent pipeline
(`plan → write → render_image → render_video → review → publish`), prompts under
`apps/api/app/prompts/`, and the Remotion templates.
