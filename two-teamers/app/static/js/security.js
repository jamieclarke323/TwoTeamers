(() => {
  window.ttFetch = (url, options = {}) => {
    const target = new URL(url, location.href);
    const headers = new Headers(options.headers);
    if (target.origin === location.origin && !["GET", "HEAD", "OPTIONS"].includes((options.method || "GET").toUpperCase())) {
      const token = document.querySelector('meta[name="csrf-token"]')?.content;
      if (token) headers.set("X-CSRF-Token", token);
    }
    return fetch(url, {...options, headers});
  };
})();
