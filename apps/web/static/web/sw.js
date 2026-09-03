/* App-shell worker.  Sensitive API responses are deliberately not cached here;
   they are stored per signed-in user by the application instead. */
// Bump this whenever the deployed frontend changes so installed phones
// retire an older worker and app shell on the next visit.
const CACHE = 'construct-shell-v13';
const FALLBACK = '/login';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([FALLBACK, '/static/web/manifest.webmanifest'])));
  self.skipWaiting();
});
self.addEventListener('activate', (event) => event.waitUntil(
  caches.keys()
    .then((keys) => Promise.all(keys.filter((key) => key.startsWith('construct-shell-') && key !== CACHE).map((key) => caches.delete(key))))
    .then(() => self.clients.claim()),
));
self.addEventListener('push', (event) => {
  const payload = event.data ? event.data.json() : {};
  event.waitUntil(self.registration.showNotification(payload.title || 'ConstructSaaS', {
    body: payload.body || 'You have a new workflow notification.',
    icon: '/static/web/icon-192.png',
    badge: '/static/web/icon-192.png',
    tag: payload.tag || 'construct-notification',
    data: { link: payload.link || '/notifications' },
  }));
});
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const destination = new URL(event.notification.data?.link || '/notifications', self.location.origin).href;
  event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((client) => client.url.startsWith(self.location.origin));
    return existing ? existing.focus().then(() => existing.navigate(destination)) : clients.openWindow(destination);
  }));
});
self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;
  const url = new URL(request.url);
  if (url.pathname.startsWith('/api/')) return;
  event.respondWith(
    fetch(request).then((response) => {
      if (response.ok && (request.mode === 'navigate' || url.pathname.startsWith('/static/'))) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    }).catch(async () => (await caches.match(request)) || (request.mode === 'navigate' ? caches.match(FALLBACK) : Response.error())),
  );
});
