// Market Intelligence Lab — Pass-Through Push Service Worker
// CRITICAL: ZERO-CACHE POLICY
// Network requests pass through directly to guarantee host code changes reflect immediately on mobile PWA.

self.addEventListener("install", (event) => {
  // Activate immediately without waiting for existing tabs to close
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Claim control over all open clients immediately
  event.waitUntil(self.clients.claim());
});

// Pass-through fetch handler: never intercept or cache HTML or JS bundles
self.addEventListener("fetch", (event) => {
  // Allow browser to perform default network fetch
  return;
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
