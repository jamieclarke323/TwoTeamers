self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil((async () => {
  const cache = await caches.open(ASSET_CACHE);
  await cache.delete("/static/img/two-teamers-app-icon.png");
  await cache.delete("/static/img/two-teamers-app-icon.svg");
  await self.clients.claim();
})()));

const OFFLINE_CACHE = "two-teamers-offline-pages-v1";
const ASSET_CACHE = "two-teamers-offline-assets-v1";

const removeExpiredPages = async (cache) => {
  for (const request of await cache.keys()) {
    const response = await cache.match(request);
    if (Number(response.headers.get("X-Offline-Expires")) <= Date.now()) await cache.delete(request);
  }
};

self.addEventListener("message", (event) => {
  if (event.data?.type !== "SAVE_OFFLINE_GAME") return;
  event.waitUntil((async () => {
    try {
      const {url, html, expiresAt, assets} = event.data;
      const target = new URL(url, self.location.origin);
      if (target.origin !== self.location.origin || !target.pathname.startsWith("/offline/quiz/")
        || !Number.isFinite(expiresAt) || expiresAt <= Date.now()
        || expiresAt > Date.now() + 8 * 60 * 60 * 1000
        || typeof html !== "string" || !Array.isArray(assets)) throw new Error("Invalid offline game download.");
      const assetCache = await caches.open(ASSET_CACHE);
      for (const path of assets) {
        const asset = new URL(path, self.location.origin);
        if (asset.origin !== self.location.origin || !asset.pathname.startsWith("/static/")) throw new Error("Invalid offline asset.");
        const response = await fetch(asset.href, {cache: "reload"});
        if (!response.ok) throw new Error(`Could not download ${asset.pathname}.`);
        await assetCache.put(asset.href, response);
      }
      const cache = await caches.open(OFFLINE_CACHE);
      await removeExpiredPages(cache);
      await cache.put(target.href, new Response(html, {
        headers: {"Content-Type": "text/html; charset=utf-8", "X-Offline-Expires": String(expiresAt)},
      }));
      event.ports[0].postMessage({saved: true});
    } catch (error) {
      event.ports[0].postMessage({error: error.message});
    }
  })());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/offline/quiz/")) {
    event.respondWith((async () => {
      const cache = await caches.open(OFFLINE_CACHE);
      await removeExpiredPages(cache);
      const saved = await cache.match(event.request);
      if (saved) return saved;
      try {
        return await fetch(event.request);
      } catch (error) {
        return new Response(
          "<!doctype html><html lang=en><meta name=viewport content='width=device-width,initial-scale=1'><title>Offline game unavailable</title><h1>Offline game unavailable</h1><p>The download has expired or was removed. Reconnect and select Play offline again.</p></html>",
          {status: 410, headers: {"Content-Type": "text/html; charset=utf-8"}},
        );
      }
    })());
  } else if (url.pathname.startsWith("/static/")) {
    event.respondWith((async () => {
      try {
        return await fetch(event.request);
      } catch (error) {
        const saved = await (await caches.open(ASSET_CACHE)).match(event.request);
        if (saved) return saved;
        throw error;
      }
    })());
  }
});

const safeNotificationTarget = (url) => {
  let target;
  try {
    target = new URL(typeof url === "string" ? url : "/", self.location.origin);
  } catch {
    return new URL("/", self.location.origin);
  }
  const allowedPath = target.pathname === "/"
    || target.pathname === "/featured"
    || target.pathname === "/profile"
    || /^\/quiz\/[a-zA-Z0-9_-]+$/.test(target.pathname);
  if (target.origin !== self.location.origin || !allowedPath) {
    return new URL("/", self.location.origin);
  }
  target.search = "";
  target.hash = "";
  return target;
};

self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch (error) {
    console.error("Could not read push notification data.", error);
  }

  if (!message || typeof message !== "object") message = {};
  const target = safeNotificationTarget(message.url);
  event.waitUntil(self.registration.showNotification(
    typeof message.title === "string" && message.title
      ? message.title
      : "Two Teamers",
    {
      body: typeof message.body === "string" && message.body
        ? message.body
        : "Open Two Teamers to play.",
      icon: "/static/img/two-teamers-app-icon-2026.png",
      badge: "/static/img/two-teamers-app-icon-2026.png",
      data: {url: target.href},
    },
  ));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = safeNotificationTarget(event.notification.data?.url);

  event.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(async (windows) => {
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin && "focus" in client) {
        try {
          const navigatedClient = "navigate" in client
            ? await client.navigate(target.href)
            : null;
          if (navigatedClient) return navigatedClient.focus();
        } catch (error) {
          console.error("Could not navigate the notification window.", error);
        }
      }
    }
    return self.clients.openWindow(target.href);
  }));
});
