(() => {
  const dialog = document.getElementById("how-to-play-dialog");
  const button = document.getElementById("how-to-play-btn");
  let autoOpenTimer;
  button?.addEventListener("click", () => {
    clearTimeout(autoOpenTimer);
    if (dialog) {
      delete dialog.dataset.autoOpenPending;
      if (!dialog.open) dialog.showModal();
    }
  });

  const lastVisitKey = "two-teamers-last-visit";
  const sevenDays = 7 * 24 * 60 * 60 * 1000;
  const now = Date.now();
  let lastVisit;
  try {
    lastVisit = Number(localStorage.getItem(lastVisitKey));
    localStorage.setItem(lastVisitKey, String(now));
  } catch (error) {
    console.warn("Could not remember the last visit for How to play. Automatic opening is disabled.", error);
    return;
  }

  if (dialog && document.body.dataset.authenticated !== "true"
      && (!Number.isFinite(lastVisit) || lastVisit <= 0 || now - lastVisit > sevenDays)) {
    dialog.dataset.autoOpenPending = "true";
    autoOpenTimer = setTimeout(() => {
      delete dialog.dataset.autoOpenPending;
      if (!dialog.open) dialog.showModal();
    }, 3000);
  }
})();
