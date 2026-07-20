const CACHE_NAME = 'pokemon-tcg-checklist-step6e-auto-refresh-v2';

const FRESH_PATHS = new Set([
  '/Pokemon-tcg-checklist/',
  '/Pokemon-tcg-checklist/index.html',
  '/Pokemon-tcg-checklist/pokemon_cards_data.json',
  '/Pokemon-tcg-checklist/pokemon_image_map.json',
  '/Pokemon-tcg-checklist/prices.json',
  '/Pokemon-tcg-checklist/price_history.json',
  '/Pokemon-tcg-checklist/pokemon_image_debug.json',
  '/Pokemon-tcg-checklist/pokemon_image_cleanup_debug.json',
  '/Pokemon-tcg-checklist/pitch_black_debug.json'
]);

function isFreshRequest(url) {
  if (url.origin !== self.location.origin) return false;
  if (FRESH_PATHS.has(url.pathname)) return true;
  return url.pathname.endsWith('.json') || url.pathname.endsWith('.html');
}

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Belangrijke databestanden altijd vers ophalen. Zo verschijnen nieuwe sets/prijzen/afbeeldingen
  // zonder telkens Ctrl+F5 of eindeloos verversen.
  if (isFreshRequest(url)) {
    event.respondWith(
      fetch(new Request(req, { cache: 'reload' }))
        .then(res => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy).catch(() => {}));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Voor iconen en statische bestanden: normaal netwerk eerst, daarna cache als fallback.
  event.respondWith(
    fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE_NAME).then(cache => {
        if (url.origin === self.location.origin) cache.put(req, copy).catch(() => {});
      });
      return res;
    }).catch(() => caches.match(req))
  );
});
