/* BIOQUEST service worker: lets the app shell open without network (field use).
   - Same-origin pages: network-first, cached copy when offline.
   - /_next/static (immutable, hashed): cache-first.
   - API calls and map tiles are NOT cached here: observations made offline go to the IndexedDB queue
     (lib/offline.ts) and sync when the connection returns; map tiles need network. */
const VERSION = "bq-shell-v2";
const SHELL = ["/", "/observations/new", "/observations", "/mission", "/manifest.webmanifest", "/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/_next/static/")) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(VERSION).then((c) => c.put(req, copy));
      return res;
    })));
    return;
  }
  e.respondWith(
    fetch(req).then((res) => {
      if (res.ok && (req.mode === "navigate" || url.pathname.startsWith("/_next/"))) {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(async () => {
      const hit = await caches.match(req, { ignoreSearch: req.mode === "navigate" });
      if (hit) return hit;
      if (req.mode === "navigate") return (await caches.match("/observations/new")) || (await caches.match("/"));
      return Response.error();
    }),
  );
});
