(() => {
  const key = "two-teamers-analytics-consent-v1";
  const banner = document.getElementById("analytics-consent");
  if (!banner) return;
  const status = document.getElementById("analytics-consent-status");
  const measurementId = "G-XZLDYJXQ8V";
  let choice = null;
  let started = false;
  const readChoice = () => {
    try {
      const stored = JSON.parse(localStorage.getItem(key));
      if (stored && ["accepted", "rejected"].includes(stored.choice)
        && Number.isFinite(stored.expiresAt) && stored.expiresAt > Date.now()) return stored.choice;
    } catch (error) {
      console.warn("Could not read analytics consent.", error);
    }
    return null;
  };
  const startAnalytics = () => {
    if (started || choice !== "accepted") return;
    started = true;
    window[`ga-disable-${measurementId}`] = false;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", measurementId, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_expires: 180 * 86400,
      page_location: location.origin + location.pathname,
      page_referrer: document.referrer ? new URL(document.referrer).origin : "",
    });
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
    script.onerror = () => { status.textContent = "Analytics could not load. The game is unaffected."; };
    document.head.appendChild(script);
  };
  const clearAnalyticsCookies = () => {
    const domains = location.hostname.split(".");
    for (const cookie of document.cookie.split(";")) {
      const name = cookie.trim().split("=")[0];
      if (name !== "_ga" && !name.startsWith("_ga_")) continue;
      document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`;
      for (let index = 0; index < domains.length - 1; index += 1) {
        document.cookie = `${name}=; Max-Age=0; Path=/; Domain=.${domains.slice(index).join(".")}; SameSite=Lax`;
      }
    }
  };
  const choose = (value) => {
    choice = value;
    try {
      localStorage.setItem(key, JSON.stringify({choice, expiresAt: Date.now() + 180 * 86400000}));
    } catch (error) {
      status.textContent = "Your browser could not save this choice. You may be asked again next visit.";
      console.warn("Could not save analytics consent.", error);
    }
    banner.hidden = true;
    if (choice === "accepted") startAnalytics();
    else {
      window[`ga-disable-${measurementId}`] = true;
      clearAnalyticsCookies();
      if (started) location.reload();
    }
    document.getElementById("analytics-settings").focus();
  };
  document.getElementById("analytics-accept").addEventListener("click", () => choose("accepted"));
  document.getElementById("analytics-reject").addEventListener("click", () => choose("rejected"));
  document.getElementById("analytics-settings").addEventListener("click", () => {
    banner.hidden = false;
    document.getElementById("analytics-reject").focus();
  });
  window.addEventListener("storage", (event) => {
    if (event.key === key || event.key === null) {
      window[`ga-disable-${measurementId}`] = true;
      location.reload();
    }
  });
  choice = readChoice();
  banner.hidden = choice !== null;
  if (choice === "accepted") startAnalytics();
  else {
    window[`ga-disable-${measurementId}`] = true;
    clearAnalyticsCookies();
  }
})();
