// Service worker: makes the app installable and keeps the token visible offline.
//
// Strategy:
//   - App shell + visited token pages are cached so they load with no network.
//   - For /t/<id> token pages we use "network-first, fall back to cache" so a
//     customer who paid online still sees their token if wifi/power dies after.
const CACHE = "tea-token-v1";
const SHELL = ["/", "/static/menu.js", "/static/token.js", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;

  // Never cache live API/WebSocket calls.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return;

  const isToken = url.pathname.startsWith("/t/");
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        // Cache token pages and static assets as we see them.
        if (isToken || url.pathname.startsWith("/static/")) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(event.request).then((r) => r || caches.match("/")))
  );
});
