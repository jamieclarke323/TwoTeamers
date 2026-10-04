// Rewarded ad adapter: showRewardedAd(name) resolves true only when the user earned the reward.
(() => {
  const config = JSON.parse(document.getElementById("ads-config")?.textContent || "{}");

  // Google Ad Placement API (AdSense H5): https://developers.google.com/ad-placement
  window.adsbygoogle = window.adsbygoogle || [];
  const adPlacement = (options) => window.adsbygoogle.push(options);

  const showAdSenseRewardedAd = (name) => new Promise((resolve) => {
    let rewarded = false;
    adPlacement({
      type: "reward",
      name,
      beforeReward: (showAdFn) => showAdFn(),
      adViewed: () => { rewarded = true; },
      adDismissed: () => { rewarded = false; },
      // Always fires, including when no ad is available.
      adBreakDone: () => resolve(rewarded),
    });
  });

  const showSimulatedRewardedAd = () => new Promise((resolve) => {
    const overlay = document.createElement("dialog");
    overlay.className = "simulated-ad";
    overlay.innerHTML = '<p class="eyebrow">Advert</p><h2>Your ad here</h2><p>Clues unlock in <strong>3</strong>...</p>';
    document.body.appendChild(overlay);
    overlay.addEventListener("cancel", (event) => event.preventDefault());
    overlay.showModal();
    let remaining = 3;
    const timer = setInterval(() => {
      remaining -= 1;
      overlay.querySelector("strong").textContent = String(remaining);
      if (remaining > 0) return;
      clearInterval(timer);
      overlay.close();
      overlay.remove();
      resolve(true);
    }, 1000);
  });

  if (config.provider === "adsense") adPlacement({preloadAdBreaks: "on", sound: "on"});

  window.TwoTeamersAds = {
    showRewardedAd: (name) => (config.provider === "adsense" ? showAdSenseRewardedAd(name) : showSimulatedRewardedAd()),
  };
})();
