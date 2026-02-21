const CACHE_NAME = 'localplay-v3';
const OFFLINE_URL = 'offline.html';

// Install event - pre-cache offline fallback page
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.add(OFFLINE_URL))
    );
    self.skipWaiting();
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        })
    );
    self.clients.claim();
});

// Fetch event - network first, fallback to cache, then offline page
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests and WebSocket
    if (event.request.method !== 'GET' || url.protocol === 'ws:' || url.protocol === 'wss:') {
        return;
    }

    // Skip backend API calls (different port locally, different host in prod)
    if (url.port === '8000' || url.hostname === 'gamesapi.revelryapp.me') {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Cache successful responses for static assets
                if (response.status === 200 && response.type === 'basic') {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }
                return response;
            })
            .catch(() => {
                // Fallback to cache
                return caches.match(event.request).then((cached) => {
                    if (cached) return cached;
                    // For navigation requests, try cached index.html (SPA) then offline page
                    if (event.request.mode === 'navigate') {
                        return caches.match('./').then((index) => index || caches.match(OFFLINE_URL));
                    }
                });
            })
    );
});
