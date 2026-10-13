(() => {
  const button = document.getElementById("guest-your-team");
  const toast = document.getElementById("home-login-toast");
  let timer;
  button?.addEventListener("click", () => {
    clearTimeout(timer);
    toast.classList.add("visible");
    timer = setTimeout(() => toast.classList.remove("visible"), 3000);
  });
})();