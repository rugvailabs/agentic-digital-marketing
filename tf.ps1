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

function Compose { docker compose @args; if ($LASTEXITCODE -ne 0) { throw "docker compose failed ($LASTEXITCODE)" } }
function Api { docker compose exec -T api @args; if ($LASTEXITCODE -ne 0) { throw "api command failed ($LASTEXITCODE)" } }
function Pnpm { pnpm @args; if ($LASTEXITCODE -ne 0) { throw "pnpm failed ($LASTEXITCODE)" } }

switch ($Target) {
  'help' {
    @'
TrendForge targets

  install    Install JS deps (pnpm install)
  up         Start postgres/redis/minio/api/worker/beat, migrate, seed
  down       Stop and remove containers (volumes kept)
  stop       Stop containers, keep them
  ps         Stack status
  logs       Tail api + worker + beat logs
  dev        Run the Next.js app on this host (run `up` first)
  migrate    alembic upgrade head
  revision   New migration:  .\tf.ps1 revision -m "add trends table"
  seed       Seed regions (idempotent)
  ingest     Run one ingest cycle now, synchronously
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
  'install'   { Pnpm install }
  'up' {
    Compose up -d --build postgres redis minio api worker beat
    Api alembic upgrade head
    Api python -m app.db.seed
    Write-Host "`nStack is up. API http://localhost:8020/health  MinIO http://localhost:9021" -ForegroundColor Green
    Write-Host "Next:  .\tf.ps1 ingest   then   .\tf.ps1 dev" -ForegroundColor Green
  }
  'down'      { Compose down }
  'stop'      { Compose stop }
  'ps'        { Compose ps }
  'logs'      { Compose logs -f --tail=100 api worker beat }
  'dev'       { Pnpm --filter @trendforge/web dev }
  'migrate'   { Api alembic upgrade head }
  'revision'  { Api alembic revision --autogenerate -m $m }
  'seed'      { Api python -m app.db.seed }
  'ingest'    { Api python -m app.tasks.run_once }
  'reset-db'  { Compose down -v; & $PSCommandPath up }
  'test'      { & $PSCommandPath test-api; & $PSCommandPath test-web }
  'test-api'  { Api pytest -q }
  'test-web'  { Pnpm --filter @trendforge/web test -- --run }
  'lint'      { Api ruff check app; Api ruff format --check app; Pnpm --filter @trendforge/web lint }
  'typecheck' { Api mypy app; Pnpm --filter @trendforge/web typecheck }
  'fmt' {
    Api ruff format app
    Api ruff check --fix app
    Pnpm prettier --write "apps/web/**/*.{ts,tsx,css}" "packages/**/*.{ts,tsx}"
  }
  'shots'     { Pnpm --filter @trendforge/web shot }
  default     { Write-Error "Unknown target '$Target'. Run .\tf.ps1 help"; exit 1 }
}
