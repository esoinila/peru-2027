
(function () {
  const TZ = window.TRIP_TZ || "America/Lima";
  const START = window.TRIP_START || "2027-03-04";
  const END = window.TRIP_END || "2027-03-17";

  function limaDate(d) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(d);
    const o = {};
    parts.forEach(p => { o[p.type] = p.value; });
    return `${o.year}-${o.month}-${o.day}`;
  }
  function limaHour(d) {
    return Number(new Intl.DateTimeFormat("en-GB", {
      timeZone: TZ, hour: "2-digit", hourCycle: "h23"
    }).format(d));
  }
  function dayNumFromDate(iso) {
    const a = new Date(START + "T12:00:00Z");
    const b = new Date(iso + "T12:00:00Z");
    return Math.round((b - a) / 86400000) + 1;
  }
  function parseQS() {
    const q = new URLSearchParams(location.search);
    if (q.get("day")) {
      sessionStorage.setItem("dayOverride", q.get("day"));
      return Number(q.get("day"));
    }
    const ov = sessionStorage.getItem("dayOverride");
    return ov ? Number(ov) : null;
  }

  const todayIso = limaDate(new Date());
  const startN = dayNumFromDate(START);
  const endN = dayNumFromDate(END);
  let n = dayNumFromDate(todayIso);
  const override = parseQS();
  if (override) n = override;
  const before = todayIso < START && !override;
  const after = todayIso > END && !override;
  const hour = limaHour(new Date());
  const band = hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";

  window.TRIP_STATE = { n, todayIso, before, after, band, override };

  document.querySelectorAll("[data-today-card]").forEach(el => {
    const daysEl = document.getElementById("trip-days-json");
    const slotsEl = document.getElementById("trip-photo-slots-json");
    const days = daysEl ? JSON.parse(daysEl.textContent) : [];
    const photoSlots = slotsEl ? JSON.parse(slotsEl.textContent) : [];
    let html = "";
    if (before) {
      const ms = new Date(START + "T12:00:00Z") - new Date();
      const dleft = Math.max(0, Math.ceil(ms / 86400000));
      const d = days.find(x => x.n === 1) || days[0];
      html = `<div class="card today" id="today-card">
        <p class="muted">Countdown · ${dleft} days to departure</p>
        <h2>Day ${d.n} · ${d.title}</h2>
        <p>${d.date} · ${d.hotelName || "—"} · ${d.altitude_m} m</p>
      </div>`;
    } else if (after) {
      html = `<div class="card today" id="today-card">
        <h2>Trip over</h2>
        <p class="muted">Photo slots to fill</p>
        <ul class="plain">${photoSlots.map(s => `<li>${s}</li>`).join("")}</ul>
      </div>`;
    } else {
      const d = days.find(x => x.n === n) || days[0];
      const frees = (d.free || []).map(f => f.from);
      const hint = frees.includes(band)
        ? `Now (${band}): free-time window`
        : `Now: ${band}`;
      html = `<div class="card today" id="today-card">
        <p class="muted">Today · Day ${d.n}</p>
        <h2>${d.title}</h2>
        <p>${d.date} · ${d.hotelName || "in transit"} · ${d.altitude_m} m</p>
        <p class="muted">${hint}</p>
        <p><a class="btn" href="day/${String(d.n).padStart(2,"0")}.html">Open day ${d.n}</a></p>
      </div>`;
    }
    el.innerHTML = html;
  });

  document.querySelectorAll("[data-look-for]").forEach(box => {
    const slug = box.getAttribute("data-look-for");
    const items = JSON.parse(box.getAttribute("data-items") || "[]");
    const key = "look:" + slug;
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) {}
    box.innerHTML = items.map((t, i) => {
      const id = slug + "-" + i;
      const on = saved[i] ? "checked" : "";
      return `<label class="check"><input type="checkbox" data-i="${i}" ${on}> <span>${t}</span></label>`;
    }).join("");
    box.addEventListener("change", () => {
      const st = {};
      box.querySelectorAll("input").forEach(inp => { st[inp.getAttribute("data-i")] = inp.checked; });
      localStorage.setItem(key, JSON.stringify(st));
    });
  });

  document.querySelectorAll("textarea[data-notes]").forEach(ta => {
    const slug = ta.getAttribute("data-notes");
    const key = "notes:" + slug;
    ta.value = localStorage.getItem(key) || "";
    ta.addEventListener("input", () => localStorage.setItem(key, ta.value));
  });

  if ("serviceWorker" in navigator) {
    const swUrl = document.querySelector("html") && (function(){
      const scripts = document.querySelectorAll("script[src]");
      // resolve sw relative to site root: same folder as app.js
      const app = [...scripts].find(s => (s.getAttribute("src")||"").includes("app.js"));
      if (!app) return "sw.js";
      return app.getAttribute("src").replace("app.js", "sw.js");
    })();
    const pill = document.getElementById("offline-pill");
    const setPill = t => { if (pill) pill.textContent = t; };
    const markReady = () => { setPill("offline ready ✓"); if (pill) pill.classList.add("ready"); };
    const watch = w => {
      if (!w) return;
      setPill("caching for offline…");
      w.addEventListener("statechange", () => {
        if (w.state === "activated") markReady();
        else if (w.state === "redundant") setPill("offline cache failed — reload on wifi");
      });
    };
    navigator.serviceWorker.register(swUrl).then(reg => {
      if (reg.active && !reg.installing && !reg.waiting) markReady();
      watch(reg.installing);
      reg.addEventListener("updatefound", () => watch(reg.installing));
    }).catch(() => setPill("sw failed"));
  }
})();
