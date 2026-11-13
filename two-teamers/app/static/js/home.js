(() => {
  const countdowns = Array.from(document.querySelectorAll("[data-closes-at]"), element => ({
    element,
    deadline: Date.parse(element.dataset.closesAt),
  }));
  const updateCountdowns = () => {
    const now = Date.now();
    for (const { element, deadline } of countdowns) {
      const secondsLeft = Math.max(0, Math.ceil((deadline - now) / 1000));
      const nextGame = element.dataset.countdownKind === "next";
      element.classList.toggle("home-countdown-urgent", secondsLeft > 0 && secondsLeft <= 3600);
      if (secondsLeft === 0) {
        element.textContent = nextGame ? "Refresh to check the next game" : "Closed";
        continue;
      }
      const hours = Math.floor(secondsLeft / 3600);
      const minutes = Math.floor((secondsLeft % 3600) / 60);
      const seconds = secondsLeft % 60;
      element.textContent = `${nextGame ? "Next game starts in" : "Closes in"} ${[hours, minutes, seconds]
        .map(value => String(value).padStart(2, "0")).join(":")}`;
    }
  };
  if (countdowns.length) {
    updateCountdowns();
    setInterval(updateCountdowns, 1000);
  }

  const button = document.getElementById("guest-your-team");
  const toast = document.getElementById("home-login-toast");
  let timer;
  button?.addEventListener("click", () => {
    clearTimeout(timer);
    toast.classList.add("visible");
    timer = setTimeout(() => toast.classList.remove("visible"), 3000);
  });
})();