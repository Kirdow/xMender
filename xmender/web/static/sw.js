// xMender service worker: makes the app installable and lets the page shell
// open without a connection. Served at /sw.js so its scope is the whole site.
//
// Strategy: network first, cache as fallback, for the shell and /static/ only.
// /api/ is never touched, so no account data is ever cached; offline, the app
// opens and shows its normal "Cannot reach xMender" message.
'use strict';

const CACHE = 'xmender-shell-v1';
const SHELL = [
  '/',
  '/docs',
  '/manifest.webmanifest',
  '/static/style.css',
  '/static/app.js',
  '/static/docs.js',
  '/static/icon.svg',
  '/static/icons/favicon-32.png',
  '/static/icons/icon-192.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});

function cacheable(url) {
  return url.pathname === '/' || url.pathname === '/docs' || url.pathname === '/manifest.webmanifest'
    || url.pathname.startsWith('/static/');
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const nav = req.mode === 'navigate';
  if (!nav && !cacheable(url)) return;

  event.respondWith((async () => {
    try {
      const res = await fetch(req);
      if (res.ok && cacheable(url)) {
        const copy = res.clone();
        event.waitUntil(caches.open(CACHE).then((c) => c.put(req, copy)));
      }
      return res;
    } catch (err) {
      const cache = await caches.open(CACHE);
      const hit = await cache.match(req, { ignoreSearch: nav });
      if (hit) return hit;
      if (nav) {
        const shell = await cache.match(url.pathname.startsWith('/docs') ? '/docs' : '/');
        if (shell) return shell;
      }
      throw err;
    }
  })());
});
