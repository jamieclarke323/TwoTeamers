(() => {
  const data = JSON.parse(document.getElementById("quiz-data").textContent);
  const input = document.getElementById("guess-input");
  const form = document.getElementById("guess-form");
  const feedback = document.getElementById("feedback");
  const toast = document.getElementById("correct-toast");
  const dialog = document.getElementById("clue-dialog");
  const shareDialog = document.getElementById("share-dialog");
  const copyShareButton = document.getElementById("copy-share-result");
  const dismissShareButton = document.getElementById("dismiss-share-result");
  const shareAgainButton = document.getElementById("share-results");
  const clipboardToast = document.getElementById("clipboard-toast");
  const clueLabels = {apps: "Apps", goals: "Goals", years: "Years", initials: "Initials"};
  let clueTarget = "all";
  let exactTimer;
  let shareText = data.shareText || "";
  let currentSolved = Number(data.solvedCount || 0);
  let totalCount = Number(data.totalPlayers || 0);
  const shareDismissedKey = `share-prompt-dismissed-${data.quizId}`;

  const request = async (path, body) => {
    const response = await fetch(`/quiz/${data.quizId}/${path}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    return response.json();
  };
  const card = (index) => document.querySelector(`.player-card[data-index="${index}"]`);
  const fillCard = (player) => {
    const element = card(player.index);
    element.classList.add("found"); element.disabled = true;
    element.innerHTML = `<strong>${escapeHtml(player.name)}</strong><span>${escapeHtml(player.home_team)}: ${escapeHtml(player.home_years)} · ${player.home_apps} apps · ${player.home_goals} goals</span><span>${escapeHtml(player.away_team)}: ${escapeHtml(player.away_years)} · ${player.away_apps} apps · ${player.away_goals} goals</span>`;
  };
  const escapeHtml = (value) => { const element = document.createElement("span"); element.textContent = String(value); return element.innerHTML; };
  const updateShareScore = (solved, total) => {
    const scoreEl = document.getElementById("share-dialog-score");
    if (!scoreEl) return;
    const s = solved ?? currentSolved;
    const t = total ?? totalCount;
    if (t > 0) {
      scoreEl.textContent = `${s}/${t}, well done!`;
    }
  };
  const showSharePrompt = (text, force = false, delayMs = 0) => {
    if (text) shareText = text;
    updateShareScore();
    const openModal = () => {
      if (shareText && (force || !sessionStorage.getItem(shareDismissedKey)) && !shareDialog.open) {
        updateShareScore();
        shareDialog.showModal();
      }
    };
    if (delayMs > 0 && !force) {
      setTimeout(openModal, delayMs);
    } else {
      openModal();
    }
  };
  const showClipboardToast = () => {
    clipboardToast.classList.add("visible");
    setTimeout(() => clipboardToast.classList.remove("visible"), 2200);
  };
  const copyTextFallback = (text) => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) throw new Error("Clipboard copy failed");
  };
  const copyShareResult = async () => {
    if (!shareText) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(shareText);
      } else {
        copyTextFallback(shareText);
      }
      sessionStorage.setItem(shareDismissedKey, "1");
      shareDialog.close();
      showClipboardToast();
    } catch (_error) {
      feedback.textContent = "Could not access the clipboard. Please allow clipboard access and try again.";
      feedback.className = "feedback wrong";
    }
  };
  const applyGuess = (result) => {
    if (result.status === "correct") {
      fillCard(result.player); input.value = ""; document.getElementById("solved-count").textContent = result.solved_count;
      currentSolved = Number(result.solved_count);
      if (result.total) totalCount = Number(result.total);
      toast.classList.add("visible"); setTimeout(() => toast.classList.remove("visible"), 1700);
      feedback.textContent = "";
      if (result.completed) {
        input.disabled = true; form.querySelector("button").disabled = true;
        document.getElementById("all-clues").disabled = true;
        document.getElementById("give-up").disabled = true;
        shareAgainButton.hidden = false;
        feedback.textContent = "You found every player.";
        showSharePrompt(result.share_text, false, 2000);
      }
    } else if (result.status !== "not_exact") { feedback.textContent = result.message || ""; feedback.className = `feedback ${result.status}`; }
  };
  input.addEventListener("input", () => {
    clearTimeout(exactTimer); const guess = input.value.trim(); if (!guess) return;
    exactTimer = setTimeout(async () => { const result = await request("exact", {guess}); if (input.value.trim() === guess) applyGuess(result); }, 250);
  });
  form.addEventListener("submit", async (event) => { event.preventDefault(); const guess = input.value.trim(); if (guess) applyGuess(await request("guess", {guess})); });
  document.getElementById("player-grid").addEventListener("click", (event) => { const target = event.target.closest(".player-card:not(.found)"); if (target) { clueTarget = Number(target.dataset.index); dialog.showModal(); } });
  document.getElementById("all-clues").addEventListener("click", () => { clueTarget = "all"; dialog.showModal(); });
  document.getElementById("show-clues").addEventListener("click", async (event) => {
    event.preventDefault(); const types = [...dialog.querySelectorAll(".clue-options input:checked")].map((item) => item.value); if (!types.length) return;
    const result = await request("clue", {types, index: clueTarget});
    if (result.status === "ad_required") { setCluesLocked(true); return; }
    result.clues?.forEach((entry) => { const holder = card(entry.index).querySelector(".clue-holder"); holder.innerHTML = Object.keys(clueLabels).filter((type) => type in entry).map((type) => `<span><strong>${clueLabels[type]}:</strong> ${escapeHtml(entry[type])}</span>`).join(""); });
    if (data.adsEnabled) setCluesLocked(true);
    dialog.close();
  });
  const setCluesLocked = (locked) => {
    if (!data.adsEnabled) return;
    const options = document.getElementById("clue-options");
    options.classList.toggle("locked", locked);
    options.querySelectorAll("input").forEach((item) => { item.disabled = locked; if (locked) item.checked = false; });
    document.getElementById("show-clues").disabled = locked;
    document.getElementById("ad-gate").hidden = !locked;
    document.getElementById("ad-gate-message").textContent = "Watch an ad to unlock clues!";
  };
  document.getElementById("watch-ad")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const message = document.getElementById("ad-gate-message");
    button.disabled = true; button.textContent = "Loading ad...";
    try {
      const watched = await window.TwoTeamersAds?.showRewardedAd("clue-unlock");
      const result = watched ? await request("clue-unlock", {}) : null;
      if (result?.status === "unlocked") setCluesLocked(false);
      else message.textContent = watched === false ? "The ad didn't finish, so clues are still locked. Please try again." : "No ad available right now. Please try again later.";
    } catch (_error) {
      message.textContent = "No ad available right now. Please try again later.";
    } finally {
      button.disabled = false; button.textContent = "Watch ad";
    }
  });
  document.getElementById("give-up").addEventListener("click", async () => {
    if (!confirm("Reveal every answer and end this game?")) return;
    const result = await request("giveup", {confirm: true});
    result.players?.forEach(fillCard);
    if (result.solved_count !== undefined) currentSolved = Number(result.solved_count);
    if (result.total) totalCount = Number(result.total);
    input.disabled = true;
    form.querySelector("button").disabled = true;
    document.getElementById("all-clues").disabled = true;
    document.getElementById("give-up").disabled = true;
    shareAgainButton.hidden = false;
    showSharePrompt(result.share_text, false, 2000);
  });
  copyShareButton.addEventListener("click", copyShareResult);
  dismissShareButton.addEventListener("click", () => {
    sessionStorage.setItem(shareDismissedKey, "1");
    shareDialog.close();
  });
  shareAgainButton.addEventListener("click", () => showSharePrompt(shareText, true));
  document.getElementById("reset").addEventListener("click", async () => { if (confirm("Clear your progress for this game?")) { await request("reset", {confirm: true}); location.reload(); } });

  const howToPlayBtn = document.getElementById("how-to-play-btn");
  const howToPlayDialog = document.getElementById("how-to-play-dialog");
  howToPlayBtn?.addEventListener("click", () => howToPlayDialog?.showModal());

  const clueInfoBtn = document.getElementById("clue-info-btn");
  const statsInfoDialog = document.getElementById("stats-info-dialog");
  clueInfoBtn?.addEventListener("click", (event) => {
    event.preventDefault();
    statsInfoDialog?.showModal();
  });

  if (data.completed || data.givenUp) showSharePrompt(shareText);
})();
