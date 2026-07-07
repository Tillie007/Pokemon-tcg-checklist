const CACHE_NAME = 'pokemon-tcg-checklist-storagefix-v1';
self.addEventListener('install', event => {
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  event.respondWith(
    fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE_NAME).then(cache => {
        if (new URL(req.url).origin === self.location.origin) cache.put(req, copy).catch(()=>{});
      });
      return res;
    }).catch(() => caches.match(req))
  );
});
