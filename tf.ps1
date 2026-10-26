<#
  TrendForge task runner for Windows (the twin of ./Makefile).

  Usage:  .\tf.ps1 <target> [-m "migration message"]
          .\tf.ps1 help
#>
param(
  [Parameter(Position = 0)][string]$Target = 'help',
  [string]$m = 'change'
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# Helper names must not collide with the command they wrap: PowerShell resolves
# names case-insensitively and prefers functions over applications, so a
# `function Pnpm { pnpm ... }` calls itself until the call depth overflows.
function Invoke-Compose { docker compose @args; if ($LASTEXITCODE -ne 0) { throw "docker compose failed ($LASTEXITCODE)" } }
function Invoke-Api { docker compose exec -T api @args; if ($LASTEXITCODE -ne 0) { throw "api command failed ($LASTEXITCODE)" } }
function Invoke-Pnpm { pnpm @args; if ($LASTEXITCODE -ne 0) { throw "pnpm failed ($LASTEXITCODE)" } }

Set-Alias Compose Invoke-Compose
Set-Alias Api Invoke-Api

switch ($Target) {
  'help' {
    @'
TrendForge targets

  install    Install JS deps (pnpm install)
  up         Start the stack (incl. the Remotion renderer), migrate, seed
  down       Stop and remove containers (volumes kept)
  stop       Stop containers, keep them
  ps         Stack status
  logs       Tail api + worker + beat logs
  dev        Run the Next.js app on this host (run `up` first)
  migrate    alembic upgrade head
  revision   New migration:  .\tf.ps1 revision -m "add trends table"
  seed       Seed regions (idempotent)
  ingest     Run one ingest cycle now, synchronously
  curate     Cluster and name the latest snapshot with Gemini
  studio     Remotion studio for the video compositions (host, port 3101)
  renderer   Rebuild and restart the renderer service
  clean-orphans      Delete rank-0 topics older than 7 days and their content
  clean-orphans-dry  Show what clean-orphans would delete
  reset-db   Drop volumes and rebuild from scratch
  test       pytest + vitest
  test-api   pytest only
  test-web   vitest only
  lint       ruff + eslint
  typecheck  mypy + tsc
  fmt        autoformat python + js
  shots      Playwright screenshots (light + dark)
'@ | Write-Host
  }
  'install'   { Invoke-Pnpm install }
  'up' {
    Compose up -d --build postgres redis minio api worker beat renderer
    Api alembic upgrade head
    Api python -m app.db.seed
    Write-Host "`nStack is up. API http://localhost:8020/health  MinIO http://localhost:9021" -ForegroundColor Green
    Write-Host "Renderer http://localhost:3100/health" -ForegroundColor Green
    Write-Host "Next:  .\tf.ps1 ingest   then   .\tf.ps1 dev" -ForegroundColor Green
  }
  'down'      { Compose down }
  'stop'      { Compose stop }
  'ps'        { Compose ps }
  'logs'      { Compose logs -f --tail=100 api worker beat renderer }
  'renderer'  { Compose up -d --build --force-recreate renderer }
  'studio' {
    # Needs a local copy of the faces: the container gets them as a
    # read-only mount, but the studio runs on this host.
    Invoke-Pnpm --filter @trendforge/remotion fonts
    Invoke-Pnpm --filter @trendforge/remotion studio --port 3101
  }
  'dev' {
    # Refuse to start behind an existing listener. A dev server left running
    # from an earlier session keeps the port, so a second `dev` lands on 3021
    # while the browser still talks to the old process. If that old process
    # has had its .next deleted underneath it, every request it serves is a
    # bare "Internal Server Error" with no overlay and no log line — which
    # looks exactly like a broken app.
    $busy = Get-NetTCPConnection -LocalPort 3020 -State Listen -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($busy) {
      $owner = (Get-Process -Id $busy.OwningProcess -ErrorAction SilentlyContinue).ProcessName
      Write-Error ("port 3020 is already served by $owner (pid $($busy.OwningProcess)). " +
        "Stop it first:  Stop-Process -Id $($busy.OwningProcess)")
      exit 1
    }
    Invoke-Pnpm --filter @trendforge/web dev
  }
  'migrate'   { Api alembic upgrade head }
  'revision'  { Api alembic revision --autogenerate -m $m }
  'seed'      { Api python -m app.db.seed }
  'ingest'    { Api python -m app.tasks.run_once }
  'curate'    { Api python -m app.tasks.curate }
  'clean-orphans'     { Api python -m app.db.maintenance }
  'clean-orphans-dry' { Api python -m app.db.maintenance --dry-run }
  'reset-db'  { Compose down -v; & $PSCommandPath up }
  'test'      { & $PSCommandPath test-api; & $PSCommandPath test-web }
  'test-api'  { Api pytest -q }
  'test-web'  { Invoke-Pnpm --filter @trendforge/web test }
  'lint'      { Api ruff check app; Api ruff format --check app; Invoke-Pnpm --filter @trendforge/web lint }
  'typecheck' { Api mypy app; Invoke-Pnpm --filter @trendforge/web typecheck }
  'fmt' {
    Api ruff format app
    Api ruff check --fix app
    Invoke-Pnpm prettier --write "apps/web/**/*.{ts,tsx,css}" "packages/**/*.{ts,tsx}"
  }
  'shots'     { Invoke-Pnpm --filter @trendforge/web shot }
  default     { Write-Error "Unknown target '$Target'. Run .\tf.ps1 help"; exit 1 }
}
