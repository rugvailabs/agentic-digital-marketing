# @trendforge/types

TypeScript types for the TrendForge API, generated from the FastAPI OpenAPI schema.

```powershell
.\tf.ps1 up                    # API must be running
pnpm --filter @trendforge/types generate
```

`src/generated/api.ts` is generated — do not hand-edit. `src/index.ts` picks the
schemas the web app actually uses and gives them short names.
