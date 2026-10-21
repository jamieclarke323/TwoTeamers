self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch (error) {
    console.error("Could not read push notification data.", error);
  }

  event.waitUntil(self.registration.showNotification(
    message.title || "Two Teamers",
    {
      body: message.body || "Open Two Teamers to play.",
      icon: "/static/img/two-teamers-app-icon-192.png",
      badge: "/static/img/two-teamers-app-icon-192.png",
      data: {url: message.url || "/"},
    },
  ));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin);
  if (target.origin !== self.location.origin) return;

  event.waitUntil(clients.matchAll({type: "window", includeUncontrolled: true}).then((windows) => {
    for (const client of windows) {
      if (client.url.startsWith(self.location.origin) && "focus" in client) {
        return client.navigate(target.href).then(() => client.focus());
      }
    }
    return clients.openWindow(target.href);
  }));
});
