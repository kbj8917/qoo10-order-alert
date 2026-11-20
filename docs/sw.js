// 앱 화면만 캐시 (네트워크 우선). GitHub API 요청은 캐시하지 않음.
const C = "qoo10-app-v2";
self.addEventListener("install", e => { e.waitUntil(caches.open(C).then(c => c.addAll(["./", "index.html", "manifest.json", "icon.svg"]))); self.skipWaiting(); });
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.includes("/data/")) return;
  e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); return r; }).catch(() => caches.match(e.request)));
});
