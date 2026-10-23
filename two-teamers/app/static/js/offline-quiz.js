(() => {
  const embedded = document.getElementById("offline-package");
  const status = document.getElementById("offline-status");
  const button = document.getElementById("play-offline");
  const showStatus = (message) => { status.textContent = message; };
  const syncSavedGame = OfflineSync.sync;
  const savedUrl = (saved) => `/offline/quiz/${saved.quizId}?download=${saved.id}`;
  const activateWorker = async () => {
    const registration = await navigator.serviceWorker.register("/service-worker.js");
    await registration.update();
    const worker = registration.installing || registration.waiting || registration.active;
    if (!worker) throw new Error("Your browser could not start offline storage.");
    if (worker.state !== "activated") await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Offline storage could not start. Please retry.")), 30000);
      const changed = () => {
        if (worker.state !== "activated" && worker.state !== "redundant") return;
        clearTimeout(timer);
        worker.removeEventListener("statechange", changed);
        if (worker.state === "activated") resolve();
        else reject(new Error("Offline storage could not start. Please retry."));
      };
      worker.addEventListener("statechange", changed);
      changed();
    });
    await navigator.serviceWorker.ready;
    return worker;
  };
  const workerMessage = (worker, message) => new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timer = setTimeout(() => reject(new Error("Saving the offline game timed out. Please retry.")), 30000);
    channel.port1.onmessage = (event) => {
      clearTimeout(timer);
      if (event.data.error) reject(new Error(event.data.error));
      else resolve(event.data);
    };
    worker.postMessage(message, [channel.port2]);
  });

  if (!embedded) {
    if (!("serviceWorker" in navigator) || !("indexedDB" in window) || !window.isSecureContext) {
      button.disabled = true;
      showStatus("Offline play requires a supported browser and HTTPS.");
      return;
    }
    const quizId = JSON.parse(document.getElementById("quiz-data").textContent).quizId;
    button.addEventListener("click", async () => {
      button.disabled = true;
      showStatus("Downloading this game for offline play...");
      try {
        const worker = await activateWorker();
        const previous = (await OfflineStorage.all()).filter((saved) => saved.quizId === quizId);
        const playable = previous.find((saved) => Date.now() < saved.expiresAt);
        if (playable) {
          await syncSavedGame(playable.id);
          const response = await fetch(`/quiz/${quizId}/offline-refresh`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({token: playable.token}),
          });
          const refreshed = await response.json();
          if (!response.ok) throw new Error(refreshed.message || "Could not refresh this offline game.");
          await workerMessage(worker, {
            type: "SAVE_OFFLINE_GAME", url: refreshed.url, html: refreshed.html,
            expiresAt: refreshed.package.expiresAt, assets: refreshed.assets,
          });
          location.assign(savedUrl(playable));
          return;
        }
        for (const saved of previous) await syncSavedGame(saved.id);
        const response = await fetch(`/quiz/${quizId}/offline-package`, {method: "POST"});
        if (!response.ok) throw new Error("This game could not be downloaded. Check your connection and its availability.");
        const downloaded = await response.json();
        await OfflineStorage.update(downloaded.package.id, () => ({
          record: {...downloaded.package, actions: [], acknowledged: 0},
        }));
        try {
          await workerMessage(worker, {
            type: "SAVE_OFFLINE_GAME", url: downloaded.url, html: downloaded.html,
            expiresAt: downloaded.package.expiresAt, assets: downloaded.assets,
          });
        } catch (error) {
          await OfflineStorage.update(downloaded.package.id, () => ({}));
          throw error;
        }
        location.assign(downloaded.url);
      } catch (error) {
        showStatus(`Offline play was not enabled: ${error.message}`);
        button.disabled = false;
      }
    });
    return;
  }

  const pack = JSON.parse(embedded.textContent);
  document.getElementById("return-online").addEventListener("click", async (event) => {
    event.preventDefault();
    const target = event.currentTarget.href;
    try {
      await syncSavedGame(pack.id);
      location.assign(target);
    } catch (error) {
      showStatus(`Your offline progress is still saved here. ${error.message}`);
      if (confirm("Offline progress could not sync. Continue online anyway? Progress will not be merged automatically if you play online first.")) {
        location.assign(target);
      }
    }
  });
  const sync = async () => {
    try {
      await syncSavedGame(pack.id);
      const saved = await OfflineStorage.get(pack.id);
      showStatus(Date.now() < pack.expiresAt
        ? `Offline mode ready until ${new Date(pack.expiresAt).toLocaleTimeString()}. Progress ${saved?.acknowledged ? "synced" : "saved on this device"}.`
        : "Offline access has expired. Progress synced; reconnect to download the game again.");
    } catch (error) {
      showStatus(`Progress is saved on this device. ${error.message} Reconnect or reopen this page to retry.`);
    }
  };

  const ready = (async () => {
    const saved = await OfflineStorage.get(pack.id);
    if (!saved) throw new Error("This offline game is no longer saved. Reconnect and download it again.");
    pack.state = saved.state;
    const data = JSON.parse(document.getElementById("quiz-data").textContent);
    data.solvedCount = saved.state.solved.length;
    data.completed = OfflineGame.completed(pack, saved.state);
    data.givenUp = saved.state.given_up;
    data.shareText = data.completed || data.givenUp ? OfflineGame.share(pack, saved.state) : "";
    document.getElementById("quiz-data").textContent = JSON.stringify(data);
    document.getElementById("solved-count").textContent = data.solvedCount;
    const escape = (value) => {
      const span = document.createElement("span");
      span.textContent = String(value);
      return span.innerHTML;
    };
    const clueLabels = {years: "Years", initials: "Initials", nationality: "Nationality"};
    for (const player of pack.players) {
      const card = document.querySelector(`.player-card[data-index="${player.index}"]`);
      const revealed = (saved.state.answer_data.revealed || []).includes(player.index)
        || (saved.state.given_up && !saved.state.solved.includes(player.index));
      const found = saved.state.solved.includes(player.index) || revealed || saved.state.given_up;
      card.classList.toggle("found", found);
      card.classList.toggle("revealed", revealed);
      card.disabled = found;
      if (found) {
        card.innerHTML = `<strong>${revealed ? "❌ " : ""}${escape(player.name)}</strong><span>${escape(pack.home)}: ${escape(player.home_years)} · ${player.home_apps} apps · ${player.home_goals} goals</span><span>${escape(pack.away)}: ${escape(player.away_years)} · ${player.away_apps} apps · ${player.away_goals} goals</span>`;
      } else {
        const clues = saved.state.answer_data.clues[String(player.index)] || [];
        card.innerHTML = `<span class="card-number">${player.index + 1}</span><strong>Unknown player</strong><span class="clue-holder">${
          clues.length ? clues.map((kind) => `<span><strong>${clueLabels[kind]}:</strong> ${escape(player.clues[kind])}</span>`).join("") : "Tap for a clue"
        }</span>`;
      }
    }
    for (const id of ["guess-input", "all-clues", "give-up"]) {
      document.getElementById(id).disabled = data.completed || data.givenUp;
    }
    document.querySelector("#guess-form button[type=submit]").disabled = data.completed || data.givenUp;
    document.getElementById("share-results").hidden = !(data.completed || data.givenUp);
    showStatus(`Saved for offline play until ${new Date(pack.expiresAt).toLocaleTimeString()}.`);
    if (pack.adsEnabled) {
      document.querySelectorAll("#clue-options input, #show-clues, #watch-ad").forEach((element) => { element.disabled = true; });
      document.getElementById("ad-gate").hidden = false;
      document.getElementById("ad-gate-message").textContent = "Ad-gated clues require returning to online play.";
    }
    sync();
  })();

  const request = async (action, body) => {
    await ready;
    const result = await OfflineStorage.update(pack.id, (saved) => {
      if (!saved || Date.now() >= saved.expiresAt) throw new Error("Offline access has expired. Reconnect and download the game again.");
      if (Date.now() < saved.issuedAt) throw new Error("Your device clock changed. Reconnect before continuing.");
      if (saved.actions.length >= 10000) throw new Error("This offline session is full. Return to online play.");
      const at = Math.max(Date.now(), saved.actions.at(-1)?.at || saved.issuedAt);
      const response = OfflineGame.apply(pack, saved.state, action, body);
      if (!["error", "ad_required", "not_exact"].includes(response.status)) {
        saved.actions.push({seq: saved.actions.length + 1, at, action, body});
      }
      return {record: saved, result: response};
    });
    sync();
    return result;
  };
  const expire = () => {
    if (Date.now() < pack.expiresAt) return;
    document.querySelectorAll("#guess-form input, #guess-form button, .game-actions button, .player-card, #show-clues").forEach((element) => { element.disabled = true; });
    showStatus("Offline access has expired. Reconnect and download the game again. Pending progress can still sync.");
    document.getElementById("player-grid").hidden = true;
    OfflineStorage.update(pack.id, (saved) => {
      if (saved) delete saved.players;
      return {record: saved};
    }).catch((error) => showStatus(`Could not clean up expired answers: ${error.message}`));
  };
  ready.then(expire).catch((error) => {
    showStatus(error.message);
    document.querySelectorAll(".game-controls button, .game-controls input, .player-card").forEach((element) => { element.disabled = true; });
  });
  setInterval(() => { expire(); sync(); }, 30000);
  window.addEventListener("online", sync);
  window.addEventListener("focus", () => { expire(); sync(); });
  globalThis.OfflineQuiz = {ready, request};
})();
