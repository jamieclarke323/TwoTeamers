(() => {
  const input = document.getElementById("club-search");
  const clubs = [...document.querySelectorAll("[data-club]")];
  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    clubs.forEach((club) => { club.hidden = !club.dataset.club.toLowerCase().includes(query); });
    document.querySelectorAll(".league-group").forEach((group) => {
      group.hidden = !group.querySelector("[data-club]:not([hidden])");
    });
  });
})();
