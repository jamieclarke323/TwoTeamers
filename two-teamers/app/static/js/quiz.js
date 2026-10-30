(async () => {
  if (window.OfflineQuiz) {
    try {
      await window.OfflineQuiz.ready;
    } catch (error) {
      console.error("Could not open the saved offline game.", error);
      return;
    }
  }
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
  const clueLabels = {years: "Years", initials: "Initials", nationality: "Nationality"};
  let clueTarget = "all";
  let exactTimer;
  let shareText = data.shareText || "";
  let currentSolved = Number(data.solvedCount || 0);
  let totalCount = Number(data.totalPlayers || 0);
  const shareDismissedKey = `share-prompt-dismissed-${data.quizId}`;

  const request = async (path, body) => {
    try {
      if (window.OfflineQuiz) return await window.OfflineQuiz.request(path, body);
      const response = await fetch(`/quiz/${data.quizId}/${path}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      return await response.json();
    } catch (error) {
      return {status: "error", message: window.OfflineQuiz ? error.message : "Could not connect. Reconnect to continue, or download a game using Play offline while online."};
    }
  };
  const card = (index) => document.querySelector(`.player-card[data-index="${index}"]`);
  const fillCard = (player, revealed = false) => {
    const element = card(player.index);
    element.classList.add("found"); element.disabled = true;
    if (revealed) element.classList.add("revealed");
    element.innerHTML = `<strong>${escapeHtml(player.name)}</strong><span>${escapeHtml(player.home_team)}: ${escapeHtml(player.home_years)}</span><span>${escapeHtml(player.away_team)}: ${escapeHtml(player.away_years)}</span>${player.nationality ? `<span>${escapeHtml(player.nationality)}</span>` : ""}`;
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
      const howToPlayDialog = document.getElementById("how-to-play-dialog");
      if (howToPlayDialog?.open) {
        howToPlayDialog.addEventListener("close", openModal, {once: true});
        return;
      }
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
  const finishGame = (result) => {
    input.disabled = true;
    form.querySelector("button[type=submit]").disabled = true;
    document.getElementById("all-clues").disabled = true;
    document.getElementById("give-up").disabled = true;
    shareAgainButton.hidden = false;
    feedback.textContent = currentSolved === totalCount ? "You found every player." : "Every answer is now resolved.";
    showSharePrompt(result.share_text, false, 2000);
  };
  const applyGuess = (result) => {
    if (result.status === "correct") {
      fillCard(result.player); input.value = ""; document.getElementById("solved-count").textContent = result.solved_count;
      currentSolved = Number(result.solved_count);
      if (result.total) totalCount = Number(result.total);
      toast.classList.add("visible"); setTimeout(() => toast.classList.remove("visible"), 1700);
      feedback.textContent = "";
      if (result.completed) {
        finishGame(result);
      }
    } else if (result.status !== "not_exact") { feedback.textContent = result.message || ""; feedback.className = `feedback ${result.status}`; }
  };
  input.addEventListener("input", () => {
    clearTimeout(exactTimer); const guess = input.value.trim(); if (!guess) return;
    exactTimer = setTimeout(async () => { const result = await request("exact", {guess}); if (input.value.trim() === guess) applyGuess(result); }, 250);
  });
  form.addEventListener("submit", async (event) => { event.preventDefault(); const guess = input.value.trim(); if (guess) applyGuess(await request("guess", {guess})); });
  const updateNationalityOption = () => {
    const giveUpAnswer = document.getElementById("give-up-answer");
    if (giveUpAnswer) giveUpAnswer.hidden = clueTarget === "all";
    const option = document.getElementById("nationality-clue-option");
    if (!option) return;
    const available = data.nationalityPlayerIndices || [];
    option.hidden = clueTarget === "all"
      ? !available.some((index) => !card(index)?.classList.contains("found"))
      : !available.includes(clueTarget);
  };
  document.getElementById("player-grid").addEventListener("click", (event) => { const target = event.target.closest(".player-card:not(.found)"); if (target) { clueTarget = Number(target.dataset.index); updateNationalityOption(); dialog.showModal(); } });
  document.getElementById("all-clues").addEventListener("click", () => { clueTarget = "all"; updateNationalityOption(); dialog.showModal(); });
  document.getElementById("give-up-answer")?.addEventListener("click", async (event) => {
    event.preventDefault();
    if (clueTarget === "all") return;
    if (!confirm("Reveal this answer? It will count as not found and show ❌ in your shared result. You can still score for the remaining players.")) return;
    const button = event.currentTarget;
    const index = clueTarget;
    clearTimeout(exactTimer);
    button.disabled = true;
    try {
      const result = await request("giveup-answer", {index, confirm: true});
      if (result.status !== "answer_revealed") {
        feedback.textContent = result.message || "Could not reveal this answer.";
        dialog.close();
        return;
      }
      fillCard(result.player, true);
      currentSolved = Number(result.solved_count);
      document.getElementById("solved-count").textContent = currentSolved;
      feedback.textContent = "Answer revealed. It will show as ❌ in your shared result.";
      dialog.close();
      if (result.completed) finishGame(result);
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("show-clues").addEventListener("click", async (event) => {
    event.preventDefault(); const types = [...dialog.querySelectorAll(".clue-options input:checked")].map((item) => item.value); if (!types.length) return;
    const result = await request("clue", {types, index: clueTarget});
    if (result.status === "ad_required") { setCluesLocked(true); return; }
    if (result.status === "error") { feedback.textContent = result.message; return; }
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
    if (result.status !== "given_up") { feedback.textContent = result.message || "Could not end this game."; return; }
    result.players?.forEach((player) => fillCard(player, !card(player.index).classList.contains("found")));
    if (result.solved_count !== undefined) currentSolved = Number(result.solved_count);
    if (result.total) totalCount = Number(result.total);
    input.disabled = true;
    form.querySelector("button[type=submit]").disabled = true;
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
  document.getElementById("reset").addEventListener("click", async () => {
    if (confirm("Clear your progress for this game?")) {
      const result = await request("reset", {confirm: true});
      if (result.status === "reset") location.reload();
      else feedback.textContent = result.message || "Could not reset this game.";
    }
  });

  const clueInfoBtn = document.getElementById("clue-info-btn");
  const statsInfoDialog = document.getElementById("stats-info-dialog");
  clueInfoBtn?.addEventListener("click", (event) => {
    event.preventDefault();
    statsInfoDialog?.showModal();
  });

  if (data.completed || data.givenUp) showSharePrompt(shareText);
})();
