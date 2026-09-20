(() => {
  const data = JSON.parse(document.getElementById("quiz-data").textContent);
  const input = document.getElementById("guess-input");
  const form = document.getElementById("guess-form");
  const feedback = document.getElementById("feedback");
  const toast = document.getElementById("correct-toast");
  const dialog = document.getElementById("clue-dialog");
  const clueLabels = {apps: "Apps", goals: "Goals", years: "Years", initials: "Initials"};
  let clueTarget = "all";
  let exactTimer;

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
  const applyGuess = (result) => {
    if (result.status === "correct") {
      fillCard(result.player); input.value = ""; document.getElementById("solved-count").textContent = result.solved_count;
      toast.classList.add("visible"); setTimeout(() => toast.classList.remove("visible"), 1700);
      feedback.textContent = "";
      if (result.completed) { input.disabled = true; form.querySelector("button").disabled = true; feedback.textContent = "You found every player."; }
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
    event.preventDefault(); const types = [...dialog.querySelectorAll("input:checked")].map((item) => item.value); if (!types.length) return;
    const result = await request("clue", {types, index: clueTarget});
    result.clues?.forEach((entry) => { const holder = card(entry.index).querySelector(".clue-holder"); holder.innerHTML = types.map((type) => `<span><strong>${clueLabels[type]}:</strong> ${escapeHtml(entry[type])}</span>`).join(""); });
    dialog.close();
  });
  document.getElementById("give-up").addEventListener("click", async () => { if (confirm("Reveal every answer and end this game?")) { const result = await request("giveup", {confirm: true}); result.players?.forEach(fillCard); input.disabled = true; } });
  document.getElementById("reset").addEventListener("click", async () => { if (confirm("Clear your progress for this game?")) { await request("reset", {confirm: true}); location.reload(); } });
})();
