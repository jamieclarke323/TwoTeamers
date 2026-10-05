(() => {
  const fixture = document.getElementById("first-playable-fixture");
  if (!fixture || window.location.hash) return;

  const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  requestAnimationFrame(() => fixture.scrollIntoView({behavior, block: "center"}));
})();
