# Shared image for the api, worker and beat services.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/srv/api \
    TZ=Asia/Kolkata

# ffmpeg is step 3: the voiceover is narrated in this image and mixed with
# the silent mp4 the renderer returns. The renderer carries its own ffmpeg
# inside Remotion's compositor, but reaching into another service's
# node_modules for a binary is not a dependency, it is a liability.
#
# libraqm is what gives Pillow complex-text shaping. Without it Devanagari,
# Tamil and Bengali render with detached vowel signs and no conjuncts, which
# CLAUDE.md's Indic requirement rules out. Pillow loads it at runtime, so
# installing the library is enough — Pillow itself needs no rebuild.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl libraqm0 ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# uv per CLAUDE.md — copied from the official distroless image, no pip bootstrap.
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv

# UV_PROJECT_ENVIRONMENT points uv at the image's own Python rather than at a
# virtualenv, which is what `pip install --system` used to do here.
#
# UV_LINK_MODE=copy because the cache below is a BuildKit mount on a different
# filesystem from the target, where uv's default hardlinking cannot work.
# Saying so up front beats a fallback warning on every build.
ENV UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/root/.cache/uv

WORKDIR /srv/api

# Dependencies, in a layer keyed on the only two files that decide them.
# Nothing under app/ can invalidate it, so an ordinary source change rebuilds
# in seconds and touches the network not at all.
#
# --locked, not --frozen. Both install from uv.lock without re-resolving,
# and resolution is the slow half on a thin connection — six and a half
# minutes for these 86 packages. The difference is what happens when
# pyproject.toml has moved and the lock has not: --frozen installs the
# stale set and says nothing, so a dependency you just added is simply
# absent and fails at import time, a long way from its cause. --locked
# stops the build with "the lockfile needs to be updated". Run `uv lock`
# and commit the result.
#
# The cache mount is what keeps the rebuild cheap even when pyproject *has*
# changed. It outlives the layer, so adding one dependency downloads one
# dependency instead of all eighty-six.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --extra dev

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
