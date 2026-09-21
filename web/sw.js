// Service Worker。初回の読み込み後は完全にオフラインで動く。
// キャッシュ名のバージョンを上げると、新しい版として配られる。

const VERSION = 'v0.1.0';
const CACHE = `studylog-${VERSION}`;

const ASSETS = [
  './',
  'index.html',
  'manifest.webmanifest',
  'css/app.css',
  'js/main.js',
  'js/db.js',
  'js/store.js',
  'js/clock.js',
  'js/codec.js',
  'js/validate.js',
  'js/transfer.js',
  'js/timer.js',
  'js/version.js',
  'js/views/components.js',
  'js/views/home.js',
  'js/views/measure.js',
  'js/views/records.js',
  'js/views/transfer.js',
  'js/views/settings.js',
  'js/views/finish-sheet.js',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  if (new URL(request.url).origin !== self.location.origin) return;

  event.respondWith(
    (async () => {
      const cached = await caches.match(request, { ignoreSearch: true });
      if (cached) return cached;
      try {
        const response = await fetch(request);
        if (response.ok && response.type === 'basic') {
          const cache = await caches.open(CACHE);
          cache.put(request, response.clone());
        }
        return response;
      } catch (error) {
        // オフラインで未キャッシュのページを開いたときは、アプリ本体を返す
        if (request.mode === 'navigate') {
          const fallback = await caches.match('index.html');
          if (fallback) return fallback;
        }
        throw error;
      }
    })(),
  );
});
