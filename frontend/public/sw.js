// Market Intelligence Lab — Pass-Through Push Service Worker
// CRITICAL: ZERO-CACHE POLICY
// Network requests pass through directly to guarantee host code changes reflect immediately on mobile PWA.

const CACHE_NAME = "mil-shell-v1";
const STATIC_ASSETS = ["/", "/manifest.webmanifest", "/icons/icon-192x192.png"];

self.addEventListener("install", (event) => {
  // Pre-cache core PWA shell assets
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Clear obsolete caches
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// Network-First with Offline Cache Fallback for navigation and static assets
self.addEventListener("fetch", (event) => {
  // Never intercept or cache API requests (/api/*) or SSE streams
  if (event.request.url.includes("/api/") || event.request.url.includes("/events/stream")) {
    return;
  }

  // Navigation requests: Network-first, fallback to cached shell
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/"))
    );
    return;
  }

  // Static assets: Stale-while-revalidate
  if (event.request.destination === "font" || event.request.destination === "image") {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const networkFetch = fetch(event.request).then((response) => {
          if (response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        }).catch(() => cached);
        return cached || networkFetch;
      })
    );
  }
});

// Native Web Push Notification Listener
self.addEventListener("push", (event) => {
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (e) {
      payload = {
        title: "MIL Market Alert",
        body: event.data.text(),
      };
    }
  }

  const title = payload.title || "MIL Causal Catalyst Alert";
  const body = payload.body || "New high-conviction market catalyst detected.";
  const url = payload.url || "/";
  const tag = payload.tag || `catalyst-${Date.now()}`;
  const icon = payload.icon || "/icons/icon-192x192.png";
  const badge = payload.badge || "/icons/badge-96x96.png";

  const options = {
    body: body,
    icon: icon,
    badge: badge,
    tag: tag,
    data: {
      url: url,
      timestamp: Date.now(),
    },
    vibrate: [120, 60, 120],
    requireInteraction: true,
    actions: [
      { action: "inspect", title: "Open Analysis" },
      { action: "dismiss", title: "Dismiss" },
    ],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// Notification Click Handler: Focus existing tab or open deep-linked target URL
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  if (event.action === "dismiss") {
    return;
  }

  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        // If an open window matches our target or origin, focus and navigate it
        for (const client of clientList) {
          if ("focus" in client) {
            client.focus();
            if ("navigate" in client) {
              return client.navigate(targetUrl);
            }
            return;
          }
        }
        // Otherwise open a new window
        if (self.clients.openWindow) {
          return self.clients.openWindow(targetUrl);
        }
      })
  );
});
