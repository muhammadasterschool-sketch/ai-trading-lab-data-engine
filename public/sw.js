// AI Trading Lab v4 — minimal service worker.
// Purpose: make the app installable (PWA / Add to Home Screen).
// Strategy: network-first for everything (app is fully dynamic); SW only
// provides an offline notice. No caching of API responses or pages.
const CACHE = 'atl-v4-shell'
const OFFLINE_URL = '/offline.html'

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll([OFFLINE_URL])).then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  // Never intercept engine websocket upgrade or API/auth traffic
  if (url.pathname.startsWith('/api/') || url.searchParams.has('XTransformPort')) {
    return
  }
  if (event.request.method !== 'GET') return

  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match(OFFLINE_URL).then(
        (r) =>
          r ??
          new Response(
            '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title><body style="background:#09090b;color:#e4e4e7;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0"><div style="text-align:center"><h1 style="color:#f59e0b">AI Trading Lab</h1><p>Cannot reach the engine server.<br>Check your connection (local server / cloud URL) and retry.</p></div></body>',
            { headers: { 'Content-Type': 'text/html' } },
          ),
      ),
    ),
  )
})
