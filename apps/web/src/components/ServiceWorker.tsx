'use client'

import { useEffect } from 'react'

/**
 * Registers the service worker, in production only.
 *
 * Not in development, and not as an oversight: a worker intercepting
 * navigations sits between the browser and Next's HMR, and the symptom is
 * an edit that does not appear until a hard reload — a long afternoon for
 * whoever hits it without knowing a worker is installed.
 *
 * It renders nothing. A component rather than a script tag because the
 * registration has to run after hydration, and a layout is a server
 * component.
 */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') return
    if (!('serviceWorker' in navigator)) return

    // After load: registration competes with the page's own requests, and
    // the first paint matters more than being installable half a second
    // sooner.
    const register = () => {
      void navigator.serviceWorker.register('/sw.js').catch((error) => {
        console.warn('[pwa] service worker did not register', error)
      })
    }

    if (document.readyState === 'complete') register()
    else window.addEventListener('load', register, { once: true })

    return () => window.removeEventListener('load', register)
  }, [])

  return null
}
