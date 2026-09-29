const CACHE_NAME = 'lv-cache-v9';
const ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/admin.js',
  '/admin-rawg.js',
  '/manifest.json',
  '/icon.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // Let API calls go through network always
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // Cache-first for static assets
  e.respondWith(
    caches.match(e.request).then((cached) => {
      return cached || fetch(e.request).then((res) => {
        // Cache new static assets
        if (res.ok && !url.pathname.startsWith('/api/')) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
        }
        return res;
      });
    }).catch(() => caches.match('/index.html'))
  );
});
