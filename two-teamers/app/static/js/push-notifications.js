(() => {
  const button = document.getElementById("push-toggle");
  const status = document.getElementById("push-status");
  if (!button || !status) return;

  const publicKey = button.dataset.publicKey;
  const supported = "serviceWorker" in navigator
    && "PushManager" in window
    && "Notification" in window;
  let currentSubscription = null;

  const setStatus = (message) => {
    status.textContent = message;
  };

  const toApplicationServerKey = (encoded) => {
    const padding = "=".repeat((4 - encoded.length % 4) % 4);
    const base64 = (encoded + padding).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
  };

  const syncButton = (subscription) => {
    currentSubscription = subscription;
    button.textContent = subscription ? "Turn off notifications on this device" : "Enable notifications";
  };

  if (!supported) {
    button.disabled = true;
    setStatus("This browser does not support push notifications. On iPhone or iPad, install the app to your Home Screen first.");
    return;
  }

  const registration = navigator.serviceWorker.register("/service-worker.js")
    .then(() => navigator.serviceWorker.ready);

  registration
    .then((serviceWorker) => serviceWorker.pushManager.getSubscription())
    .then(syncButton)
    .catch((error) => {
      button.disabled = true;
      setStatus("Notifications could not be initialized. Please reload and try again.");
      console.error("Could not initialize push notifications.", error);
    });

  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const serviceWorker = await registration;
      if (currentSubscription) {
        const response = await fetch("/push/unsubscribe", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({endpoint: currentSubscription.endpoint}),
        });
        if (!response.ok) throw new Error("The notification setting could not be updated.");
        await currentSubscription.unsubscribe();
        syncButton(null);
        setStatus("Notifications are off on this device.");
        return;
      }

      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus(permission === "denied"
          ? "Notifications are blocked in your browser settings."
          : "Notifications were not enabled.");
        return;
      }
      const subscription = await serviceWorker.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: toApplicationServerKey(publicKey),
      });
      const response = await fetch("/push/subscribe", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(subscription),
      });
      if (!response.ok) {
        await subscription.unsubscribe();
        const result = await response.json().catch(() => ({}));
        throw new Error(result.error || "The notification setting could not be saved.");
      }
      syncButton(subscription);
      setStatus("Notifications are enabled on this device.");
    } catch (error) {
      setStatus(error.message || "Notifications could not be updated. Please try again.");
      console.error("Could not update push notification settings.", error);
    } finally {
      button.disabled = false;
    }
  });
})();
