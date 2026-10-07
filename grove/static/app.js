(function () {
  "use strict";

  var ORDER = window.GROVE_WIDGETS.map(function (w) { return w[0]; });  // default order
  var WIDGETS = {};                             // id -> title
  window.GROVE_WIDGETS.forEach(function (w) { WIDGETS[w[0]] = w[1]; });
  var ICONS = { weather: "cloud-sun", news: "newspaper", links: "link-45deg" };
  var STORAGE_KEY = "grove.layout.v1";
  var REFRESH_MS = 10 * 60 * 1000;

  var grid = document.getElementById("grid");
  var latest = {};                              // last /api/widgets response
  var state = load();

  // ---------- layout state (saved per browser) ----------

  function defaults(columns) {
    var layout = [];
    for (var i = 0; i < columns; i++) layout.push([]);
    ORDER.forEach(function (id, i) { layout[i % columns].push(id); });
    return { columns: columns, layout: layout, hidden: [] };
  }

  function load() {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY)); } catch (e) { /* private mode */ }
    return normalize(saved || defaults(3));
  }

  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
  }

  // Keep the saved layout valid: right column count, known widgets only, every visible one placed.
  function normalize(s) {
    var columns = s.columns === 2 ? 2 : 3;
    var hidden = (s.hidden || []).filter(function (id) { return id in WIDGETS; });
    var layout = [];
    for (var i = 0; i < columns; i++) layout.push([]);
    var placed = {};
    (s.layout || []).forEach(function (col, i) {
      col.forEach(function (id) {
        if (id in WIDGETS && !placed[id] && hidden.indexOf(id) < 0) {
          layout[Math.min(i, columns - 1)].push(id);
          placed[id] = true;
        }
      });
    });
    ORDER.forEach(function (id) {
      if (!placed[id] && hidden.indexOf(id) < 0) shortest(layout).push(id);
    });
    return { columns: columns, layout: layout, hidden: hidden };
  }

  function shortest(layout) {
    return layout.reduce(function (a, b) { return b.length < a.length ? b : a; });
  }

  // ---------- helpers ----------

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function icon(name) { return el("i", "bi bi-" + name); }

  function link(url, text) {
    var a = el("a", null, text);
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
    return a;
  }

  function ago(iso) {
    if (!iso) return "";
    var s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m ago";
    if (s < 86400) return Math.round(s / 3600) + "h ago";
    return Math.round(s / 86400) + "d ago";
  }

  function weekday(isoDate, i) {
    if (i === 0) return "Today";
    var d = new Date(isoDate + "T12:00:00");
    return d.toLocaleDateString(undefined, { weekday: "short" });
  }

  // ---------- widget renderers ----------

  var render = {
    weather: function (d, body) {
      var now = el("div", "wx-now");
      now.appendChild(icon(d.icon));
      var t = el("div");
      t.appendChild(el("div", "wx-temp", d.temp + "°"));
      t.appendChild(el("div", null, d.text));
      now.appendChild(t);
      var more = el("div", "ms-auto text-end small text-muted");
      var today = d.days[0];
      if (today) more.appendChild(el("div", null, "H " + today.high + "°  ·  L " + today.low + "°"));
      more.appendChild(el("div", null, "Feels like " + d.feels_like + "°"));
      if (d.sunset) more.appendChild(el("div", null, "Sunset " + d.sunset));
      now.appendChild(more);
      body.appendChild(now);

      if (d.hours && d.hours.length) {
        var hours = el("div", "wx-hours");
        d.hours.forEach(function (h) {
          var c = el("div");
          c.title = h.text;
          c.appendChild(el("div", null, h.label));
          c.appendChild(icon(h.icon));
          c.appendChild(el("div", null, h.temp + "°"));
          hours.appendChild(c);
        });
        body.appendChild(hours);
        return;
      }
      var days = el("div", "wx-days");
      d.days.forEach(function (day, i) {
        var c = el("div");
        c.title = day.text + (day.rain_chance != null ? ", " + day.rain_chance + "% rain" : "");
        c.appendChild(el("div", "fw-semibold", weekday(day.date, i)));
        c.appendChild(icon(day.icon));
        c.appendChild(el("span", null, day.high + "° "));
        c.appendChild(el("span", "lo", day.low + "°"));
        if (day.rain_chance >= 30) c.appendChild(el("div", "text-muted", day.rain_chance + "%"));
        days.appendChild(c);
      });
      body.appendChild(days);
    },

    news: function (d, body) {
      var ul = el("ul", "news-list");
      d.items.forEach(function (item) {
        var li = el("li");
        if (item.image) {
          var img = el("img");
          img.src = item.image;
          img.alt = "";
          img.loading = "lazy";
          img.onerror = function () { img.remove(); };
          li.appendChild(img);
        }
        var text = el("div");
        text.appendChild(link(item.url, item.title));
        if (item.date) text.appendChild(el("div", "small text-muted", ago(item.date)));
        li.appendChild(text);
        ul.appendChild(li);
      });
      body.appendChild(ul);
    },

    links: function (d, body) {
      var g = el("div", "links-grid");
      d.links.forEach(function (l) {
        var a = link(l.url, null);
        var i = icon(l.icon);
        if (l.color) i.style.setProperty("--tile", l.color);
        a.appendChild(i);
        a.appendChild(el("span", null, l.label));
        g.appendChild(a);
      });
      body.appendChild(g);
    }
  };

  function card(id) {
    var w = latest[id] || {};
    var node = el("section", "widget");
    node.dataset.widget = id;
    node.setAttribute("aria-label", WIDGETS[id]);

    var head = el("div", "widget-head");
    head.appendChild(icon(ICONS[id] || "square"));
    // "Campus News" -> "Campus <accent>News</accent>", like Today's "What's for Breakfast?"
    var words = WIDGETS[id].split(" ");
    var title = el("span", null, words.length > 1 ? words.slice(0, -1).join(" ") + " " : "");
    title.appendChild(el("span", words.length > 1 ? "accent" : null, words[words.length - 1]));
    head.appendChild(title);
    if (w.updated_ago) head.appendChild(el("span", "updated", w.updated_ago));
    node.appendChild(head);

    if (w.stale) node.appendChild(el("div", "widget-stale", "Couldn't refresh lately; showing older data."));

    var body = el("div", "widget-body");
    if (w.data) {
      try { render[id](w.data, body); }
      catch (e) { body.replaceChildren(el("div", "widget-note", "Couldn't show this widget.")); }
    } else {
      body.appendChild(el("div", "widget-note", w.message || "Loading…"));
    }
    node.appendChild(body);
    return node;
  }

  function draw() {
    grid.replaceChildren();
    state.layout.forEach(function (col, i) {
      var c = el("div", "grove-col");
      c.dataset.col = i;
      col.forEach(function (id) { c.appendChild(card(id)); });
      grid.appendChild(c);
    });
    if (arranging) setDraggable(true);
  }

  function drawGreeting() {
    var g = latest.greeting && latest.greeting.data;
    if (!g) return;
    document.getElementById("greeting-hello").textContent = g.hello;
    document.getElementById("greeting-date").textContent = g.date;
    var week = document.getElementById("greeting-week");
    week.textContent = g.semester_week ? "Week " + g.semester_week + " of the semester" : "";
    week.classList.toggle("d-none", !g.semester_week);
  }

  // ---------- your name (saved per browser) ----------

  var NAME_KEY = "grove.name";
  var nameBtn = document.getElementById("hero-name");
  var nameInput = document.getElementById("name-input");

  function getName() {
    try { return localStorage.getItem(NAME_KEY) || ""; } catch (e) { return ""; }
  }

  function setName(name) {
    name = (name || "").trim().slice(0, 40);
    try {
      if (name) localStorage.setItem(NAME_KEY, name); else localStorage.removeItem(NAME_KEY);
    } catch (e) { /* ignore */ }
    nameBtn.textContent = name || "Rebel";
  }

  nameBtn.addEventListener("click", function () {
    var input = el("input", "hero-name-input");
    input.value = getName();
    input.placeholder = "your name";
    input.maxLength = 40;
    input.setAttribute("aria-label", "Your name");
    nameBtn.replaceWith(input);
    input.focus();
    var done = false;
    function finish(save) {
      if (done) return;
      done = true;
      if (save) setName(input.value);
      input.replaceWith(nameBtn);
    }
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", function () { finish(true); });
  });

  nameInput.addEventListener("change", function () { setName(nameInput.value); });
  setName(getName());

  // ---------- study mode: big clock + focus timer ----------

  var studyBtn = document.getElementById("study-btn");
  var clock = document.getElementById("study-clock");
  var timeEl = document.getElementById("study-time");
  var goBtn = document.getElementById("study-go");
  var timer = { minutes: 25, left: 25 * 60, endsAt: null, tick: null };

  function mmss(sec) {
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function drawClock() {
    clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function drawTimer() {
    timeEl.textContent = mmss(timer.left);
    goBtn.textContent = timer.endsAt ? "Pause" : (timer.left < timer.minutes * 60 ? "Resume" : "Start");
    document.title = timer.endsAt ? mmss(timer.left) + " · Grove" : "Grove";
  }

  function chime() {
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.25, 0.5].forEach(function (t) {
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = 880;
        g.gain.setValueAtTime(0.15, ctx.currentTime + t);
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.2);
        o.connect(g); g.connect(ctx.destination);
        o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.2);
      });
    } catch (e) { /* no audio */ }
  }

  function stopTimer() {
    clearInterval(timer.tick);
    timer.tick = null;
    timer.endsAt = null;
  }

  function resetTimer(minutes) {
    stopTimer();
    if (minutes) timer.minutes = minutes;
    timer.left = timer.minutes * 60;
    drawTimer();
  }

  goBtn.addEventListener("click", function () {
    if (timer.endsAt) { stopTimer(); drawTimer(); return; }
    timer.endsAt = Date.now() + timer.left * 1000;
    timer.tick = setInterval(function () {
      timer.left = Math.max(0, Math.round((timer.endsAt - Date.now()) / 1000));
      if (timer.left === 0) { stopTimer(); chime(); document.title = "Time's up · Grove"; resetTimer(); return; }
      drawTimer();
    }, 250);
    drawTimer();
  });

  document.getElementById("study-reset").addEventListener("click", function () { resetTimer(); });

  document.querySelectorAll(".study-modes button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".study-modes button").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active");
      resetTimer(Number(b.dataset.minutes));
    });
  });

  studyBtn.addEventListener("click", function () {
    var on = !document.body.classList.contains("studying");
    if (on && arranging) setArranging(false);
    document.body.classList.toggle("studying", on);
    studyBtn.textContent = on ? "exit study mode" : "study mode";
  });

  drawClock();
  setInterval(drawClock, 1000);

  function refresh() {
    fetch("/api/widgets", { headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        latest = data;
        drawGreeting();
        if (!arranging) draw();
      })
      .catch(function () { /* keep showing what we have */ });
  }

  // ---------- arrange mode (drag and drop) ----------

  var arranging = false;
  var dragged = null;
  var arrangeBtn = document.getElementById("arrange-btn");
  var doneBtn = document.getElementById("arrange-done");

  function setDraggable(on) {
    grid.querySelectorAll(".widget").forEach(function (w) { w.draggable = on; });
  }

  function setArranging(on) {
    arranging = on;
    document.body.classList.toggle("arranging", on);
    document.getElementById("arrange-hint").classList.toggle("d-none", !on);
    doneBtn.classList.toggle("d-none", !on);
    arrangeBtn.classList.toggle("d-none", on);
    setDraggable(on);
    if (!on) draw();
  }

  arrangeBtn.addEventListener("click", function () { setArranging(true); });
  doneBtn.addEventListener("click", function () { setArranging(false); });

  grid.addEventListener("dragstart", function (e) {
    dragged = e.target.closest(".widget");
    if (!dragged) return;
    dragged.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragged.dataset.widget);
  });

  grid.addEventListener("dragend", function () {
    if (dragged) dragged.classList.remove("dragging");
    dragged = null;
    // Read the new order straight from the DOM.
    state.layout = Array.prototype.map.call(grid.children, function (col) {
      return Array.prototype.map.call(col.querySelectorAll(".widget"), function (w) {
        return w.dataset.widget;
      });
    });
    save();
  });

  grid.addEventListener("dragover", function (e) {
    if (!dragged) return;
    var col = e.target.closest(".grove-col");
    if (!col) return;
    e.preventDefault();
    var after = null;
    col.querySelectorAll(".widget:not(.dragging)").forEach(function (w) {
      var box = w.getBoundingClientRect();
      if (after === null && e.clientY < box.top + box.height / 2) after = w;
    });
    if (after) col.insertBefore(dragged, after); else col.appendChild(dragged);
  });

  grid.addEventListener("drop", function (e) { e.preventDefault(); });

  // ---------- settings ----------

  var toggles = document.querySelectorAll("#widget-toggles input");
  var columnRadios = document.querySelectorAll("input[name=columns]");

  function syncSettings() {
    toggles.forEach(function (t) { t.checked = state.hidden.indexOf(t.dataset.widget) < 0; });
    columnRadios.forEach(function (r) { r.checked = Number(r.value) === state.columns; });
  }

  toggles.forEach(function (t) {
    t.addEventListener("change", function () {
      var id = t.dataset.widget;
      state.hidden = state.hidden.filter(function (h) { return h !== id; });
      if (!t.checked) state.hidden.push(id);
      state = normalize(state);
      save();
      draw();
    });
  });

  columnRadios.forEach(function (r) {
    r.addEventListener("change", function () {
      var columns = Number(r.value);
      // Moving 3 -> 2 folds the last column into the shortest remaining one.
      var flat = state.layout;
      if (columns < flat.length) {
        var extra = flat.slice(columns).reduce(function (a, c) { return a.concat(c); }, []);
        flat = flat.slice(0, columns);
        extra.forEach(function (id) { shortest(flat).push(id); });
      }
      state = normalize({ columns: columns, layout: flat, hidden: state.hidden });
      save();
      draw();
    });
  });

  document.getElementById("reset-layout").addEventListener("click", function () {
    state = defaults(state.columns);
    save();
    syncSettings();
    draw();
  });

  document.getElementById("settings").addEventListener("show.bs.modal", function () {
    syncSettings();
    nameInput.value = getName();
  });

  // ---------- start ----------

  draw();
  refresh();
  setInterval(refresh, REFRESH_MS);
})();
