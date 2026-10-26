# The Remotion renderer service.
#
# Separate from the Python image on purpose: this one carries a Chromium, and
# api/worker/beat have no use for it. See server/index.ts.
FROM node:22-bookworm-slim

ENV TZ=Asia/Kolkata \
    # Remotion downloads a headless shell into this directory at build time,
    # so a cold start does not begin with a 150MB fetch.
    REMOTION_BROWSER_CACHE=/srv/renderer/.chromium

# What Chromium links against. Remotion's own list; without these the browser
# starts and then dies with an error that names no missing library.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl fonts-liberation tzdata \
      libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcairo2 \
      libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libnspr4 libnss3 \
      libpango-1.0-0 libpangocairo-1.0-0 libx11-6 libxcb1 libxcomposite1 \
      libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/renderer

# Deps first so editing a composition does not reinstall node_modules. No
# pnpm workspace here: this package has no workspace dependencies, and
# installing it standalone keeps the image from carrying the web app too.
#
# Optional deps are not optional: Remotion ships its compositor — the ffmpeg
# and encoder bindings — as a per-platform optional package, and omitting it
# produces an image that boots, bundles, and then fails every render with
# "Cannot find module @remotion/compositor-linux-x64-gnu".
#
# NODE_ENV is deliberately not set to production here either. It would skip
# devDependencies, and @remotion/cli is what `remotion studio` needs when this
# image is used interactively.
COPY package.json ./
RUN npm install --no-audit --no-fund

# Fetch the browser now rather than on the first render. Through the renderer
# API rather than the CLI: the API is a runtime dependency of this service and
# the CLI is not, so this keeps working whatever the install flags are.
RUN node -e "require('@remotion/renderer').ensureBrowser().then(() => console.log('browser ready'))"

COPY tsconfig.json remotion.config.ts ./
COPY src ./src
COPY server ./server
COPY scripts ./scripts

# public/fonts is a read-only mount of apps/api/app/assets/fonts (see
# docker-compose.yml), so both renderers read one set of files.
RUN mkdir -p public/fonts

EXPOSE 3100
CMD ["npx", "tsx", "server/index.ts"]
