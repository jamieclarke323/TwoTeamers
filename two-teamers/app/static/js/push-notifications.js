(() => {
  const button = document.getElementById("push-toggle");
  const status = document.getElementById("push-status");
  const preferencesForm = document.getElementById("push-preferences");
  const successToast = document.getElementById("push-success-toast");
  if (!button || !status || !preferencesForm) return;

  const publicKey = button.dataset.publicKey;
  const csrfToken = button.dataset.csrfToken;
  const pushConfigured = button.dataset.pushConfigured === "true";
  const supported = "serviceWorker" in navigator
    && "PushManager" in window
    && "Notification" in window;
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches
    || window.navigator.standalone === true;
  const iosInstallRequired = isIOS && !isStandalone;
  let currentSubscription = null;
  let registrationPromise = null;
  let toastTimer = null;

  const setStatus = (message) => {
    status.textContent = message;
  };

  const showSuccess = () => {
    if (!successToast) return;
    successToast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(
      () => successToast.classList.remove("visible"),
      2800,
    );
  };

  const toApplicationServerKey = (encoded) => {
    const padding = "=".repeat((4 - encoded.length % 4) % 4);
    const base64 = (encoded + padding).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
  };

  const syncPreferences = (preferences) => {
    document.getElementById("daily-game-notifications").checked
      = preferences.daily_game_notifications;
    document.getElementById("my-team-notifications").checked
      = preferences.my_team_notifications;
    preferencesForm.hidden = false;
  };

  const postJson = async (url, body) => {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "The notification setting could not be saved.");
    }
    return result;
  };

  const subscribeOnServer = async (subscription) => {
    const preferences = await postJson("/push/subscribe", subscription.toJSON());
    syncPreferences(preferences);
  };

  const syncButton = (subscription) => {
    currentSubscription = subscription;
    if (subscription) {
      button.textContent = "This device is subscribed";
      button.disabled = true;
    } else {
      button.textContent = "Enable Notifications";
    }
  };

  if (iosInstallRequired) {
    button.disabled = true;
    setStatus("On iPhone or iPad, add Two Teamers to your Home Screen before enabling notifications.");
  } else if (!supported) {
    button.disabled = true;
    setStatus("This browser does not support push notifications.");
  } else if (!pushConfigured) {
    button.disabled = true;
    setStatus("The site owner needs to finish notification setup.");
  } else {
    registrationPromise = navigator.serviceWorker.register("/service-worker.js")
      .then(() => navigator.serviceWorker.ready);
    registrationPromise
      .then((serviceWorker) => serviceWorker.pushManager.getSubscription())
      .then(async (subscription) => {
        syncButton(subscription);
        if (subscription && Notification.permission === "granted") {
          try {
            await subscribeOnServer(subscription);
            setStatus("Notifications are active on this device.");
          } catch (error) {
            button.disabled = false;
            button.textContent = "Retry notification setup";
            setStatus(error.message || "Notifications could not be synchronized. Please retry.");
            console.error("Could not synchronize the push subscription.", error);
          }
        } else if (!subscription && button.dataset.hasSubscriptions === "true") {
          preferencesForm.hidden = false;
          setStatus("Manage reminders for your subscribed devices.");
        }
      })
      .catch((error) => {
        button.disabled = false;
        setStatus("Notifications could not be initialized. Please reload and try again.");
        console.error("Could not initialize push notifications.", error);
      });
  }

  button.addEventListener("click", async () => {
    if (!supported || !pushConfigured || iosInstallRequired) return;
    button.disabled = true;
    try {
      const permissionRequest = Notification.permission === "granted"
        ? Promise.resolve("granted")
        : Notification.requestPermission();
      const permission = await permissionRequest;
      if (permission !== "granted") {
        button.disabled = false;
        setStatus(permission === "denied"
          ? "Notifications are blocked in your browser settings."
          : "Notifications were not enabled.");
        return;
      }

      const serviceWorker = await registrationPromise;
      const subscription = currentSubscription
        || await serviceWorker.pushManager.getSubscription()
        || await serviceWorker.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: toApplicationServerKey(publicKey),
        });
      currentSubscription = subscription;
      const preferences = await postJson("/push/subscribe", subscription.toJSON());
      syncPreferences(preferences);
      button.disabled = true;
      setStatus("Notifications are enabled on this device.");
    } catch (error) {
      button.disabled = false;
      button.textContent = currentSubscription
        ? "Retry notification setup"
        : "Enable Notifications";
      setStatus(error.message || "Notifications could not be updated. Please try again.");
      console.error("Could not enable push notifications.", error);
    }
  });

  preferencesForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const updateButton = document.getElementById("update-push-preferences");
    updateButton.disabled = true;
    try {
      const preferences = await postJson("/push/preferences", {
        daily_game_notifications:
          document.getElementById("daily-game-notifications").checked,
        my_team_notifications:
          document.getElementById("my-team-notifications").checked,
      });
      syncPreferences(preferences);
      setStatus("Your notification preferences have been saved.");
      showSuccess();
    } catch (error) {
      setStatus(error.message || "Preferences could not be saved. Please try again.");
      console.error("Could not update push notification preferences.", error);
    } finally {
      updateButton.disabled = false;
    }
  });
})();
