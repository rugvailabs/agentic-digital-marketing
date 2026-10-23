# apps/worker

Celery worker + Celery Beat. **There is no separate Python package here** —
per CLAUDE.md the worker runs the *same* package as the API (`apps/api/app`),
so tasks and models can share SQLAlchemy sessions, adapters and settings
without a second dependency tree to keep in sync.

What lives where:

| Thing                       | Path                                  |
| --------------------------- | ------------------------------------- |
| Celery app + beat schedule  | `apps/api/app/tasks/celery_app.py`    |
| Ingest + merge tasks        | `apps/api/app/tasks/ingest.py`        |
| Synchronous dev runner      | `apps/api/app/tasks/run_once.py`      |
| Container definition        | `apps/api/Dockerfile` (shared image)  |
| Service definitions         | `docker-compose.yml` → `worker`, `beat` |

Run it:

```powershell
.\tf.ps1 up            # starts worker + beat alongside the api
docker compose logs -f worker beat
.\tf.ps1 ingest        # trigger one cycle synchronously, no worker involved
```

Celery has no supported Windows worker pool, which is why `worker` and `beat`
are container-only. Don't try `celery worker` from PowerShell.
