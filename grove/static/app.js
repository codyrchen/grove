(function () {
  "use strict";

  var ORDER = window.GROVE_WIDGETS.map(function (w) { return w[0]; });  // default order
  var WIDGETS = {};                             // id -> title
  window.GROVE_WIDGETS.forEach(function (w) { WIDGETS[w[0]] = w[1]; });
  var ICONS = { weather: "cloud-sun", news: "newspaper", links: "link-45deg", gameday: "trophy",
                countdowns: "hourglass-split", square: "shop", tonight: "stars", dining: "cup-hot",
                classes: "journal-bookmark" };
  var CRN_KEY = "grove.crns";
  var classesEnabled = false;                   // the server has a term's classes to look up
  var foodOnly = false;                         // "Free food" filter on the Tonight card
  var ROLES = window.GROVE_ROLES;               // role -> widgets it starts with
  var ROLE_KEY = "grove.role";
  var COUNTDOWN_KEY = "grove.countdowns";
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

  // ---------- game helpers ----------

  function sportLabel(g) {
    return g.sport === "football" ? "" : " · " + g.sport.charAt(0).toUpperCase() + g.sport.slice(1);
  }

  function matchup(g) {
    if (g.home === false) return "at " + g.opponent;
    if (g.home === null && g.location) return "vs. " + g.opponent + " (" + g.location + ")";
    return "vs. " + g.opponent;
  }

  function gameDate(g) {
    return g.all_day ? new Date(g.start + "T12:00:00") : new Date(g.start);
  }

  function shortDate(g) {
    return gameDate(g).toLocaleDateString([], { month: "short", day: "numeric" });
  }

  function gameTime(g) {
    var d = gameDate(g);
    var day = d.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
    if (g.all_day) return day + " · time TBA";
    return day + " · " + d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function countdown(g) {
    if (g.live) return "In progress";
    if (g.all_day) return "";
    var mins = Math.round((new Date(g.start).getTime() - Date.now()) / 60000);
    if (mins <= 0) return "Kicking off";
    if (mins < 60) return "Starts in " + mins + " min";
    if (mins < 48 * 60) return "Starts in " + Math.floor(mins / 60) + "h " + (mins % 60) + "m";
    return "In " + Math.round(mins / 1440) + " days";
  }

  // "Ole Miss 24 – 17 LSU" with LIVE / FINAL, from ESPN's scoreboard.
  var SPORT_NAMES = { football: "", basketball: "Basketball", mbb: "Basketball",
                      "womens-basketball": "Women's basketball", wbb: "Women's basketball", baseball: "Baseball" };
  var BANNER_SPORTS = ["football", "basketball", "mbb", "womens-basketball", "wbb"];

  function sportName(sport) {
    return sport in SPORT_NAMES ? SPORT_NAMES[sport] : sport.charAt(0).toUpperCase() + sport.slice(1);
  }

  function scoreLine(sc) {
    return "Ole Miss " + sc.us + " – " + sc.them + " " + sc.opponent;
  }

  function scoreboard(sc) {
    var box = el("div", "game-score " + (sc.state === "in" ? "is-live" : sc.won ? "is-win" : sc.won === false ? "is-loss" : ""));
    var name = sportName(sc.sport || "football");
    if (sc.state === "in") box.appendChild(el("div", "game-badge live", (name ? name + " · " : "") + "LIVE · " + sc.detail));
    else box.appendChild(el("div", "game-label", (name ? name + " · " : "") + (sc.detail || "Final")));
    var line = el("div", "game-score-line");
    line.appendChild(el("span", "game-score-team", "Ole Miss"));
    line.appendChild(el("span", "game-score-num", sc.us + " – " + sc.them));
    line.appendChild(el("span", "game-score-team", sc.opponent));
    box.appendChild(line);
    if (sc.state === "post" && sc.won !== null) {
      box.appendChild(el("div", "game-result", (sc.won ? "W " : "L ") + Math.max(sc.us, sc.them) + "–" +
        Math.min(sc.us, sc.them) + (sc.home ? " vs. " : " at ") + sc.opponent));
    } else if (sc.tv) {
      box.appendChild(el("div", "game-extra", sc.tv));
    }
    return box;
  }

  // Game-day mode: a red banner under the greeting on football game days, a hint during game week.
  function drawGameday() {
    var pill = document.getElementById("gameday-pill");
    var d = latest.gameday && latest.gameday.data;
    var today = d && d.today, week = d && d.this_week;
    var boards = (d && d.scores) || [];
    // The banner shows a live football or basketball game, else a football win.
    var sc = boards.filter(function (g) { return g.state === "in" && BANNER_SPORTS.indexOf(g.sport || "football") >= 0; })[0] ||
             boards.filter(function (g) { return g.state === "post" && g.won && (g.sport || "football") === "football"; })[0];
    document.body.classList.toggle("gameday", !!today || !!(sc && sc.state === "in" && (sc.sport || "football") === "football"));
    pill.classList.remove("live", "win");
    if (sc && sc.state === "in") {
      var label = sportName(sc.sport || "football");
      pill.textContent = "LIVE" + (label ? " " + label.toLowerCase() : "") + ": " + scoreLine(sc) + " · " + sc.detail;
      pill.classList.add("live");
    } else if (sc && sc.state === "post" && sc.won) {
      pill.textContent = "Rebels win! " + scoreLine(sc);
      pill.classList.add("win");
    } else if (today) {
      pill.textContent = "It's game day! Ole Miss " + matchup(today) +
        (today.all_day ? "" : " · " + new Date(today.start).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
    } else if (week) {
      pill.textContent = "Game week: " + matchup(week) + " on " +
        gameDate(week).toLocaleDateString([], { weekday: "long" });
    }
    var winning = sc && (sc.state === "in" || (sc.state === "post" && sc.won));
    pill.classList.toggle("d-none", !(today || week || winning));
  }

  // Check every minute while a game is on (or about to start), every 10 minutes otherwise.
  function nextRefreshMs() {
    var d = latest.gameday && latest.gameday.data;
    if (d && (d.scores || []).some(function (g) { return g.state === "in"; })) return 60 * 1000;
    var t = d && d.today;
    if (t && !t.all_day) {
      var mins = (new Date(t.start).getTime() - Date.now()) / 60000;
      if (mins < 60 && mins > -360) return 60 * 1000;
    }
    return REFRESH_MS;
  }

  // ---------- my classes (CRNs saved per browser) ----------

  function getCrns() {
    try { return (localStorage.getItem(CRN_KEY) || "").trim(); } catch (e) { return ""; }
  }

  function loadClasses() {
    var crns = getCrns();
    var role = getRole();
    if (!crns || role !== "student" || !classesEnabled) {
      latest.classes = { data: { set_up: true, crns: "" }, empty: !classesEnabled };
      drawClassPill();
      return Promise.resolve();
    }
    return fetch("/api/classes?crns=" + encodeURIComponent(crns), { headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        data.crns = crns;
        latest.classes = { data: data, empty: !data.set_up };
        drawClassPill();
      })
      .catch(function () { /* keep what we have */ });
  }

  // "Next: CSCI 211 at 1:00 PM · Weir Hall 106" under the greeting, for today's classes.
  function drawClassPill() {
    var pill = document.getElementById("class-pill");
    var d = latest.classes && latest.classes.data;
    var n = d && d.next;
    var show = n && n.day === "Today" && getRole() === "student";
    if (show) {
      pill.textContent = (n.in_progress ? "In class: " : "Next: ") + n.label + " at " + n.time +
        (n.where ? " · " + n.where : "");
    }
    pill.classList.toggle("d-none", !show);
  }

  // ---------- personal countdowns (saved per browser) ----------

  function getCountdowns() {
    try {
      var list = JSON.parse(localStorage.getItem(COUNTDOWN_KEY)) || [];
      return Array.isArray(list) ? list.filter(function (e) { return e && e.name && e.date; }) : [];
    } catch (e) { return []; }
  }

  function saveCountdowns(list) {
    try { localStorage.setItem(COUNTDOWN_KEY, JSON.stringify(list)); } catch (e) { /* ignore */ }
    draw();
  }

  function removeCountdown(i) {
    var list = getCountdowns();
    list.splice(i, 1);
    saveCountdowns(list);
  }

  // Whole days from today (in your time zone) to a YYYY-MM-DD date.
  function daysUntil(iso) {
    var p = iso.split("-").map(Number), t = new Date();
    var target = Date.UTC(p[0], p[1] - 1, p[2]);
    var today = Date.UTC(t.getFullYear(), t.getMonth(), t.getDate());
    return Math.round((target - today) / 86400000);
  }

  function countdownForm() {
    var wrap = el("div", "countdown-add");
    var open = el("button", "countdown-add-btn", "+ Add a countdown");
    open.type = "button";
    var form = el("form", "countdown-form d-none");
    var name = el("input");
    name.placeholder = getRole() === "student" ? "Spring Break" : "Back in Oxford";
    name.maxLength = 40;
    name.required = true;
    name.setAttribute("aria-label", "Countdown name");
    var when = el("input");
    when.type = "date";
    when.required = true;
    when.setAttribute("aria-label", "Date");
    var save = el("button", "study-go", "Add");
    save.type = "submit";
    form.appendChild(name); form.appendChild(when); form.appendChild(save);
    open.addEventListener("click", function () {
      open.classList.add("d-none");
      form.classList.remove("d-none");
      name.focus();
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!name.value.trim() || !when.value) return;
      var list = getCountdowns();
      list.push({ name: name.value.trim().slice(0, 40), date: when.value });
      saveCountdowns(list.slice(-10));
    });
    wrap.appendChild(open);
    wrap.appendChild(form);
    return wrap;
  }

  // ---------- events ----------

  function eventTime(e, withDay) {
    if (e.happening && !e.all_day) return "Now";
    var d = e.all_day ? new Date(e.start + "T12:00:00") : new Date(e.start);
    var day = withDay ? d.toLocaleDateString([], { weekday: "short" }) + " " : "";
    if (e.all_day) return day + (withDay ? "" : "All day");
    return day + d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function eventList(label, list, withDay) {
    var wrap = el("div", "event-group");
    wrap.appendChild(el("div", "game-label", label));
    var ul = el("ul", "event-list" + (withDay ? " with-day" : ""));
    list.forEach(function (e) {
      var li = el("li");
      li.appendChild(el("span", "event-time" + (e.happening ? " now" : ""), eventTime(e, withDay)));
      var text = el("div", "event-text");
      text.appendChild(e.url ? link(e.url, e.title) : el("span", null, e.title));
      var meta = [e.location].filter(Boolean).join(" · ");
      if (meta || e.food) {
        var m = el("div", "event-meta", meta);
        if (e.food) m.appendChild(el("span", "event-food", "Free food"));
        text.appendChild(m);
      }
      li.appendChild(text);
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
    return wrap;
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

    gameday: function (d, body) {
      var boards = (d.scores || []).slice(0, 2);
      var upcoming = d.upcoming;
      if (boards.length) {
        boards.forEach(function (sc) { body.appendChild(scoreboard(sc)); });
        // Games on a scoreboard are still in the schedule while they're on; don't show them twice.
        upcoming = upcoming.filter(function (g) {
          return !boards.some(function (sc) {
            return g.sport === sc.sport && Math.abs(new Date(g.start) - new Date(sc.start)) < 6 * 3600000;
          });
        });
        if (!upcoming.length) return;
      }
      if (!upcoming.length) {
        body.appendChild(el("div", "widget-note", "No games on the schedule right now."));
        return;
      }
      d = Object.assign({}, d, { upcoming: upcoming });
      var next = d.upcoming[0];
      var big = el("div", "game-next" + (d.today === null ? "" : " is-today"));
      if (next.live) big.appendChild(el("div", "game-badge live", "LIVE"));
      else if (d.today && d.today.start === next.start) big.appendChild(el("div", "game-badge", "GAME DAY"));
      else big.appendChild(el("div", "game-label", "Next up" + sportLabel(next)));
      big.appendChild(el("div", "game-matchup", matchup(next)));
      big.appendChild(el("div", "game-when", gameTime(next)));
      var extra = [countdown(next), next.tv].filter(Boolean).join(" · ");
      if (extra) big.appendChild(el("div", "game-extra", extra));
      if (next.forecast) {
        var f = next.forecast;
        var fc = el("div", "game-forecast");
        fc.appendChild(icon(f.icon));
        fc.appendChild(el("span", null, "Kickoff: " + f.temp + "° · " + f.text +
          (f.rain ? " · " + f.rain + "% rain" : "")));
        big.appendChild(fc);
      }
      if (d.notes) big.appendChild(el("div", "game-note", d.notes));
      body.appendChild(big);

      // Parking, shuttles, bag policy... for home game week and game day.
      var homeSoon = next.home && (d.today || d.this_week) && next.sport === "football";
      if (homeSoon && d.tips.length) {
        var tips = el("div", "game-tips");
        tips.appendChild(el("div", "game-label", "Game-day info"));
        d.tips.forEach(function (t) {
          var row = el("div", "game-tip");
          row.appendChild(t.url ? link(t.url, t.title) : el("strong", null, t.title));
          if (t.text) row.appendChild(el("span", null, " · " + t.text));
          tips.appendChild(row);
        });
        body.appendChild(tips);
      }

      var rest = d.upcoming.slice(1);
      if (rest.length) {
        var ul = el("ul", "game-list");
        rest.forEach(function (g) {
          var li = el("li");
          li.appendChild(el("span", "game-list-when", shortDate(g)));
          li.appendChild(el("span", null, matchup(g) + sportLabel(g)));
          ul.appendChild(li);
        });
        body.appendChild(ul);
      }
    },

    countdowns: function (d, body) {
      var items = [];
      if (getRole() === "student") {
        d.academic.forEach(function (e) { items.push({ name: e.name, date: e.date, days: e.days }); });
      }
      getCountdowns().forEach(function (e, i) {
        var days = daysUntil(e.date);
        if (days >= 0) items.push({ name: e.name, date: e.date, days: days, personal: i });
      });
      items.sort(function (a, b) { return a.days - b.days; });

      if (items.length) {
        var ul = el("ul", "countdown-list");
        items.forEach(function (e) {
          var li = el("li");
          var num = el("div", "countdown-days", e.days === 0 ? "Today" : String(e.days));
          if (e.days > 0) num.appendChild(el("small", null, e.days === 1 ? "day" : "days"));
          li.appendChild(num);
          li.appendChild(el("div", "countdown-name", e.name));
          if (e.personal !== undefined) {
            var x = el("button", "countdown-remove", "×");
            x.type = "button";
            x.title = "Remove";
            x.setAttribute("aria-label", "Remove " + e.name);
            x.addEventListener("click", function () { removeCountdown(e.personal); });
            li.appendChild(x);
          }
          ul.appendChild(li);
        });
        body.appendChild(ul);
      } else {
        body.appendChild(el("div", "widget-note mb-2",
          getRole() === "student" ? "Add a countdown to spring break, a trip or a big game."
                                  : "Counting down to your next trip back to Oxford?"));
      }
      body.appendChild(countdownForm());
    },

    classes: function (d, body) {
      if (!d.set_up) {
        body.appendChild(el("div", "widget-note", "My Classes isn't turned on for this term yet."));
        return;
      }
      if (!d.crns) {
        body.appendChild(el("div", "widget-note mb-2", "Add your CRNs to see your next class and where it is."));
        var open = el("button", "countdown-add-btn", "+ Add my classes");
        open.type = "button";
        open.addEventListener("click", function () {
          bootstrap.Modal.getOrCreateInstance(document.getElementById("settings")).show();
          setTimeout(function () { document.getElementById("crn-input").focus(); }, 400);
        });
        body.appendChild(open);
        return;
      }
      if (d.next) {
        var big = el("div", "class-next");
        big.appendChild(el("div", "game-label", d.next.in_progress ? "In class now" : "Next class"));
        big.appendChild(el("div", "class-next-label", d.next.label));
        big.appendChild(el("div", "class-next-when",
          (d.next.in_progress ? "Started " : (d.next.day === "Today" ? "" : d.next.day + " ")) + d.next.time +
          (d.next.where ? " · " + d.next.where : "")));
        if (!d.next.in_progress && d.next.day === "Today") {
          var mins = Math.round((new Date(d.next.start).getTime() - Date.now()) / 60000);
          if (mins > 0) big.appendChild(el("div", "game-extra",
            mins < 60 ? "Starts in " + mins + " min" : "Starts in " + Math.floor(mins / 60) + "h " + (mins % 60) + "m"));
        }
        body.appendChild(big);
      } else {
        body.appendChild(el("div", "widget-note", "No more classes this week."));
      }
      var rest = d.today.filter(function (o) { return !d.next || o.start !== d.next.start; });
      if (rest.length) {
        var ul = el("ul", "game-list");
        rest.forEach(function (o) {
          var li = el("li");
          li.appendChild(el("span", "game-list-when", o.time));
          li.appendChild(el("span", null, o.label + (o.where ? " · " + o.where : "")));
          ul.appendChild(li);
        });
        body.appendChild(ul);
      }
      if (d.missing && d.missing.length) {
        body.appendChild(el("div", "widget-note mt-2", "Couldn't find CRN " + d.missing.join(", ") +
          " this term. Check it in Settings."));
      }
    },

    dining: function (d, body) {
      body.appendChild(el("div", "game-label",
        (d.late_night ? "Late night · " : "") + d.open_count + " open now"));
      var ul = el("ul", "dining-list");
      d.places.forEach(function (p) {
        var li = el("li", p.open ? "is-open" : "is-closed");
        li.appendChild(el("span", "dining-dot"));
        var text = el("div", "dining-text");
        text.appendChild(el("div", "dining-name", p.name));
        text.appendChild(el("div", "dining-status" + (p.closing_soon ? " soon" : ""), p.text));
        li.appendChild(text);
        if (p.menu_url) li.appendChild(link(p.menu_url, "Menu"));
        ul.appendChild(li);
      });
      body.appendChild(ul);
    },

    tonight: function (d, body) {
      if (d.food_count) {
        var chips = el("div", "event-chips");
        [["All", false], ["Free food (" + d.food_count + ")", true]].forEach(function (c) {
          var b = el("button", "event-chip" + (foodOnly === c[1] ? " active" : ""), c[0]);
          b.type = "button";
          b.setAttribute("aria-pressed", String(foodOnly === c[1]));
          b.addEventListener("click", function () { foodOnly = c[1]; draw(); });
          chips.appendChild(b);
        });
        body.appendChild(chips);
      }
      function keep(e) { return !foodOnly || e.food; }
      var today = d.today.filter(keep), soon = d.soon.filter(keep);
      if (today.length) body.appendChild(eventList("Today", today, false));
      if (soon.length) body.appendChild(eventList("Coming up", soon, true));
      if (!today.length && !soon.length) {
        body.appendChild(el("div", "widget-note", foodOnly ? "No free food on the calendar right now."
                                                            : "Nothing on the calendar yet."));
      }
    },

    square: function (d, body) {
      body.appendChild(el("div", "game-label", "This week on the Square"));
      var name = d.url ? link(d.url, d.name) : el("span", null, d.name);
      var h = el("div", "square-name");
      h.appendChild(name);
      body.appendChild(h);
      if (d.blurb) body.appendChild(el("div", "square-blurb", d.blurb));
      if (d.deal) body.appendChild(el("div", "square-deal", d.deal));
    },

    links: function (d, body) {
      var g = el("div", "links-grid");
      d.links.forEach(function (l) {
        var a = link(l.url, null);
        a.appendChild(icon(l.icon));
        a.appendChild(el("span", null, l.label));
        g.appendChild(a);
      });
      body.appendChild(g);
    }
  };

  function card(id) {
    var w = latest[id] || {};
    if (w.empty && !arranging) return null;     // nothing to show yet (e.g. no Square features)
    var node = el("section", "widget");
    node.dataset.widget = id;
    node.setAttribute("aria-label", WIDGETS[id]);

    var head = el("div", "widget-head");
    head.appendChild(icon(ICONS[id] || "square"));
    head.appendChild(el("span", "widget-title", WIDGETS[id]));
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
      col.forEach(function (id) {
        var node = card(id);
        if (node) c.appendChild(node);
      });
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
    var showWeek = g.semester_week && getRole() === "student";
    week.textContent = showWeek ? "Week " + g.semester_week + " of the semester" : "";
    week.classList.toggle("d-none", !showWeek);

    var moment = document.getElementById("moment-pill");
    var m = g.snow ? { message: "Snow in Oxford! Stay warm, Rebels." } : g.moment;
    moment.textContent = m ? m.message : "";
    moment.classList.toggle("d-none", !m);
    document.body.classList.toggle("finals", !!(g.moment && g.moment.mode === "finals"));
    setSnow(!!g.snow);

    var trivia = document.getElementById("trivia");
    trivia.textContent = g.trivia ? "Did you know? " + g.trivia : "";
    trivia.classList.toggle("d-none", !g.trivia);
  }

  // Snow day: a few drifting flakes (skipped for people who prefer reduced motion).
  function setSnow(on) {
    var layer = document.getElementById("snow");
    if (!on || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      if (layer) layer.remove();
      return;
    }
    if (layer) return;
    layer = el("div", "snow");
    layer.id = "snow";
    layer.setAttribute("aria-hidden", "true");
    for (var i = 0; i < 40; i++) {
      var f = el("span", null, "❄");
      f.style.left = Math.random() * 100 + "%";
      f.style.animationDuration = 8 + Math.random() * 10 + "s";
      f.style.animationDelay = -Math.random() * 15 + "s";
      f.style.fontSize = 8 + Math.random() * 14 + "px";
      layer.appendChild(f);
    }
    document.body.appendChild(layer);
  }

  // ---------- who you are: student, fan or alum (saved per browser) ----------

  function getRole() {
    try { return ROLES[localStorage.getItem(ROLE_KEY)] ? localStorage.getItem(ROLE_KEY) : "student"; }
    catch (e) { return "student"; }
  }

  function hasRole() {
    try { return !!ROLES[localStorage.getItem(ROLE_KEY)]; } catch (e) { return false; }
  }

  function setRole(role) {
    try { localStorage.setItem(ROLE_KEY, role); } catch (e) { /* ignore */ }
    state = defaults(state.columns);
    state.hidden = ORDER.filter(function (id) { return ROLES[role].indexOf(id) < 0; });
    state = normalize(state);
    save();
    draw();
    drawGreeting();
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

  // ---------- search ----------
  // "om parking" searches olemiss.edu. In the Chrome extension, the query goes to the extension,
  // which searches with the person's own default search engine (chrome.search).

  var SEARCH_KEY = "grove.search";
  var searchForm = document.getElementById("search");
  var searchInput = document.getElementById("search-input");
  var searchToggle = document.getElementById("search-toggle");

  function searchQuery(text) {
    var m = /^om\s+(.+)/i.exec(text);
    return m ? "site:olemiss.edu " + m[1] : text;
  }

  // The extension page that frames us, if any (Chrome lists ancestor origins).
  function extensionParent() {
    if (window.top === window || !location.ancestorOrigins || !location.ancestorOrigins.length) return null;
    var origin = location.ancestorOrigins[0];
    return origin.indexOf("chrome-extension://") === 0 ? origin : null;
  }

  searchForm.addEventListener("submit", function (e) {
    var text = searchInput.value.trim();
    if (!text) { e.preventDefault(); return; }
    var q = searchQuery(text);
    var parent = extensionParent();
    if (parent) {
      e.preventDefault();
      window.parent.postMessage({ type: "grove-search", query: q }, parent);
      return;
    }
    searchInput.value = q;  // the form submits to Google in the same tab
  });

  function searchShown() {
    try { return localStorage.getItem(SEARCH_KEY) !== "off"; } catch (e) { return true; }
  }

  function applySearch() {
    document.body.classList.toggle("search-hidden", !searchShown());
  }

  searchToggle.addEventListener("change", function () {
    try { localStorage.setItem(SEARCH_KEY, searchToggle.checked ? "on" : "off"); } catch (e) { /* ignore */ }
    applySearch();
  });

  // "/" jumps to the search bar, unless you're already typing somewhere.
  document.addEventListener("keydown", function (e) {
    var t = e.target;
    var typing = t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);
    if (e.key === "/" && !typing && searchShown() && !document.body.classList.contains("studying")) {
      e.preventDefault();
      searchInput.focus();
    }
  });

  applySearch();
  if (searchShown() && window.matchMedia("(min-width: 768px)").matches) searchInput.focus();

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
        var classesData = latest.classes;
        classesEnabled = !(data.classes && data.classes.empty);
        latest = data;
        latest.classes = classesData || { data: { set_up: true, crns: "" }, empty: true };
        drawGreeting();
        drawGameday();
        return loadClasses();
      })
      .then(function () {
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

  document.getElementById("crn-input").addEventListener("change", function (e) {
    var crns = e.target.value.split(/[\s,]+/).filter(function (c) { return /^\d{1,6}$/.test(c); }).slice(0, 12);
    e.target.value = crns.join(", ");
    try { localStorage.setItem(CRN_KEY, crns.join(",")); } catch (err) { /* ignore */ }
    loadClasses().then(draw);
  });

  document.getElementById("role-select").addEventListener("change", function (e) {
    setRole(e.target.value);
    syncSettings();
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
    searchToggle.checked = searchShown();
    document.getElementById("crn-input").value = getCrns();
    document.getElementById("role-select").value = getRole();
  });

  // ---------- first visit: welcome ----------

  function welcome() {
    var modalEl = document.getElementById("welcome");
    if (hasRole() || !window.bootstrap) return;
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    var nameEl = document.getElementById("welcome-name");
    modalEl.querySelectorAll(".role-choice").forEach(function (b) {
      b.addEventListener("click", function () {
        if (nameEl.value.trim()) setName(nameEl.value);
        setRole(b.dataset.role);
        modal.hide();
      });
    });
    modalEl.addEventListener("shown.bs.modal", function () { nameEl.focus(); }, { once: true });
    modal.show();
  }

  // ---------- start ----------

  draw();
  refresh();
  (function schedule() {
    setTimeout(function () { refresh(); schedule(); }, nextRefreshMs());
  })();
  welcome();
})();
