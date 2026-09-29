// Service worker: offline support for the app shell.
//  - code (HTML/JS/CSS): network first, cached copy when offline, so a deploy
//    is picked up on the next load without bumping anything.
//  - other static files (icons, fonts): cache first.
//  - /api/: never touched.
// Bump CACHE_NAME only to drop stale cached files (e.g. after deleting one).
const CACHE_NAME = 'lv-cache-v14';

const SHELL = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-64.png',
  '/icon-192.png',
  '/css/base.css',
  '/css/login.css',
  '/css/navbar.css',
  '/css/home.css',
  '/css/modal.css',
  '/css/admin.css',
  '/css/profile.css',
  '/js/main.js',
];

const isCode = (url) => url.pathname === '/' || /\.(html|js|css)$/.test(url.pathname);

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

async function fromNetwork(request) {
  const res = await fetch(request);
  if (res.ok) {
    const copy = res.clone();
    caches.open(CACHE_NAME).then((c) => c.put(request, copy));
  }
  return res;
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;

  if (isCode(url)) {
    e.respondWith(
      fromNetwork(e.request).catch(async () => (await caches.match(e.request)) || caches.match('/index.html')),
    );
    return;
  }

  e.respondWith(
    caches.match(e.request).then((cached) => cached || fromNetwork(e.request)).catch(() => caches.match('/index.html')),
  );
});
