/**
 * The service worker. Deliberately small.
 *
 * Its job is not to make the app work offline — a trend board that is
 * offline is a board of yesterday's trends, which is worse than an honest
 * "you are offline". Its job is to make the app installable and to replace
 * the browser's dinosaur with a page that says what happened and offers to
 * retry, which is the whole of what a user can do about it.
 *
 * So: network first for everything, a tiny cache of the shell for the
 * offline page, and no caching of anything from the API. A cached board is
 * a lie about what is trending.
 */

const VERSION = 'trendforge-v1'
const SHELL = ['/offline']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(VERSION)
      .then((cache) => cache.addAll(SHELL))
      // skipWaiting, because there is no state in a page here worth
      // protecting from a mid-session swap, and a worker that waits for
      // every tab to close never updates on a phone.
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event

  // Only GET, and only this origin. A POST that the worker retried would
  // generate a post twice; an API response that it cached would be a board
  // claiming to be current and not being.
  if (request.method !== 'GET') return
  if (new URL(request.url).origin !== self.location.origin) return

  // Navigations get the offline page when the network is gone. Everything
  // else just fails, which is what a missing image or script should do.
  if (request.mode !== 'navigate') return

  event.respondWith(
    fetch(request).catch(() =>
      caches.match('/offline').then((cached) => cached ?? Response.error()),
    ),
  )
})
