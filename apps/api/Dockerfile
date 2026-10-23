# Shared image for the api, worker and beat services.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/srv/api \
    TZ=Asia/Kolkata

# libraqm is what gives Pillow complex-text shaping. Without it Devanagari,
# Tamil and Bengali render with detached vowel signs and no conjuncts, which
# CLAUDE.md's Indic requirement rules out. Pillow loads it at runtime, so
# installing the library is enough — Pillow itself needs no rebuild.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl libraqm0 \
 && rm -rf /var/lib/apt/lists/*

# uv per CLAUDE.md — copied from the official distroless image, no pip bootstrap.
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv

WORKDIR /srv/api

# Deps only, so edits to app/ don't invalidate the layer. The source itself is
# bind-mounted in dev (see docker-compose.yml) and PYTHONPATH picks it up.
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml --extra dev

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
