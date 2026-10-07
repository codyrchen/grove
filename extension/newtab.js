(function () {
  "use strict";

  var url = (window.GROVE_URL || "").replace(/\/$/, "");
  var frame = document.getElementById("grove");
  var fallback = document.getElementById("fallback");
  var note = document.getElementById("note");
  var clock = document.getElementById("clock");

  function tick() {
    clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  tick();
  var timer = setInterval(tick, 1000);

  function offline() {
    note.textContent = "Grove can't load right now. Your clock still works. ";
    var retry = document.createElement("a");
    retry.href = "#";
    retry.textContent = "Try again";
    retry.addEventListener("click", function (e) { e.preventDefault(); location.reload(); });
    note.appendChild(retry);
  }

  if (!url) { offline(); return; }

  // Searches typed into Grove arrive here and go to the person's own default search engine.
  window.addEventListener("message", function (e) {
    if (e.source !== frame.contentWindow || e.origin !== new URL(url).origin) return;
    var data = e.data || {};
    if (data.type !== "grove-search" || typeof data.query !== "string" || !data.query.trim()) return;
    var text = data.query.trim().slice(0, 500);
    if (window.chrome && chrome.search && chrome.search.query) {
      chrome.search.query({ text: text, disposition: "CURRENT_TAB" });
    } else {
      location.href = "https://www.google.com/search?q=" + encodeURIComponent(text);
    }
  });

  // Check the site is reachable first: a cross-origin iframe can't report load errors.
  fetch(url + "/healthz", { mode: "no-cors", cache: "no-store" })
    .then(function () {
      frame.addEventListener("load", function () {
        frame.hidden = false;
        fallback.hidden = true;
        clearInterval(timer);
      }, { once: true });
      frame.src = url + "/?source=extension";
    })
    .catch(offline);
})();
