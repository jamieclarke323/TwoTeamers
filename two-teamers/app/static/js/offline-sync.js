(() => {
  const syncing = new Map();
  const blocked = new Map();
  const sync = (id) => {
    if (syncing.has(id)) return syncing.get(id);
    const operation = (async () => {
      let saved = await OfflineStorage.get(id);
      if (blocked.has(id)) throw new Error(blocked.get(id));
      while (saved && saved.actions.some((event) => event.seq > saved.acknowledged)) {
        if (!navigator.onLine) throw new Error("Reconnect to sync your progress.");
        const batch = saved.actions.filter((event) => event.seq > saved.acknowledged).slice(0, 500);
        const response = await fetch(`/quiz/${saved.quizId}/offline-sync`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({token: saved.token, actions: batch}),
        });
        const result = await response.json();
        if (!response.ok) {
          const message = result.message || "Progress could not be synced.";
          if ([400, 403, 409, 410].includes(response.status)) blocked.set(id, message);
          throw new Error(message);
        }
        await OfflineStorage.update(id, (latest) => {
          if (latest) latest.acknowledged = Math.max(latest.acknowledged, result.acknowledged);
          return {record: latest};
        });
        saved = await OfflineStorage.get(id);
      }
    })().finally(() => syncing.delete(id));
    syncing.set(id, operation);
    return operation;
  };
  globalThis.OfflineSync = {sync};

  if (!("indexedDB" in window) || document.getElementById("offline-package")) return;
  const showStatus = (message) => {
    let status = document.getElementById("offline-status");
    if (!status) {
      status = document.createElement("p");
      status.id = "offline-status";
      status.setAttribute("role", "status");
      document.querySelector("main").prepend(status);
    }
    status.textContent = message;
  };
  const syncPending = async () => {
    try {
      const errors = [];
      let uploaded = false;
      for (const saved of await OfflineStorage.all()) {
        if (Date.now() >= saved.expiresAt) await OfflineStorage.update(saved.id, (latest) => {
          if (latest) delete latest.players;
          return {record: latest};
        });
        if (saved.actions.some((event) => event.seq > saved.acknowledged)) {
          try {
            await sync(saved.id);
            uploaded = true;
          } catch (error) {
            errors.push(`${saved.home} vs ${saved.away}: ${error.message}`);
          }
        }
      }
      if (errors.length) showStatus(`Offline progress is still saved on this device. ${errors.join(" ")} Reconnect or reopen this page to retry.`);
      else if (uploaded) showStatus("Saved offline progress has synced. Reload an already-open online game to see it.");
    } catch (error) {
      showStatus(`Could not access offline progress: ${error.message}`);
    }
  };
  syncPending();
  window.addEventListener("online", syncPending);
  window.addEventListener("focus", syncPending);
  setInterval(syncPending, 30000);
})();
