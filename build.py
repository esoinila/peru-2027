#!/usr/bin/env python3
"""Generate docs/ from data/trip.json. stdlib only (except optional tile HTTP)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import sys
import time
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "trip.json"
PINS = ROOT / "data" / "globe-pins-peru.json"
DOCS = ROOT / "docs"
VENDOR = DOCS / "vendor"
IMG_SRC = ROOT / "docs" / "img"

LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_IMAGES = [
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
]
TILE_TMPL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"


def cache_version(trip: dict) -> str:
    raw = json.dumps(trip, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def esc(s) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def rel(from_path: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, from_path.parent).replace("\\", "/")


def hotel_by_id(trip, hid):
    if not hid:
        return None
    for h in trip["hotels"]:
        if h["id"] == hid:
            return h
    return None


def site_by_slug(trip, slug):
    for s in trip["sites"]:
        if s["slug"] == slug:
            return s
    return None


def zoom_for(precision: str) -> int:
    return {"point": 15, "approx": 13, "region": 11}.get(precision or "approx", 13)


def maps_links(lat, lon, name):
    g = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=walking"
    geo = f"geo:{lat},{lon}?q={lat},{lon}({urllib.parse.quote(name)})"
    return g, geo


# --- minimal PNG ---
def write_png(path: Path, w: int, h: int, rgb=(28, 18, 12), text="P"):
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    rows = []
    r, g, b = rgb
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            row += bytes([r, g, b])
        rows.append(bytes(row))
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def ensure_leaflet():
    VENDOR.mkdir(parents=True, exist_ok=True)
    js = VENDOR / "leaflet.js"
    css = VENDOR / "leaflet.css"
    if not js.exists():
        print("Downloading Leaflet JS…")
        urllib.request.urlretrieve(LEAFLET_JS, js)
    if not css.exists():
        print("Downloading Leaflet CSS…")
        urllib.request.urlretrieve(LEAFLET_CSS, css)
        css_txt = css.read_text(encoding="utf-8")
        css_txt = css_txt.replace("images/", "images/")
        css.write_text(css_txt, encoding="utf-8")
    imgd = VENDOR / "images"
    imgd.mkdir(exist_ok=True)
    for url in LEAFLET_IMAGES:
        dest = imgd / url.rsplit("/", 1)[-1]
        if not dest.exists():
            urllib.request.urlretrieve(url, dest)


def nav_html(here: Path, active: str) -> str:
    def a(key, href_path, label):
        cls = "active" if active == key else ""
        href = rel(here, href_path)
        return f'<a class="{cls}" href="{href}">{label}</a>'

    return f"""<nav class="bottom-nav" aria-label="Main">
  {a("today", DOCS / "index.html", "Today")}
  {a("days", DOCS / "index.html#days", "Days")}
  {a("sites", DOCS / "sites.html", "Sites")}
  {a("hotels", DOCS / "hotels.html", "Hotels")}
  {a("contacts", DOCS / "contacts.html", "Contacts")}
</nav>"""


def page_shell(here: Path, title: str, body: str, extra_head="", extra_js="", active="today", depth=0):
    css = rel(here, DOCS / "app.css")
    js = rel(here, DOCS / "app.js")
    man = rel(here, DOCS / "manifest.webmanifest")
    ico = rel(here, DOCS / "img" / "icon-192.png")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1c120c">
<title>{esc(title)}</title>
<link rel="manifest" href="{man}">
<link rel="icon" href="{ico}">
<link rel="apple-touch-icon" href="{ico}">
<link rel="stylesheet" href="{css}">
{extra_head}
</head>
<body>
<main class="wrap">
{body}
</main>
{nav_html(here, active)}
<script src="{js}"></script>
{extra_js}
</body>
</html>
"""


def tag_badges(tags):
    return "".join(f'<span class="badge">{esc(t)}</span>' for t in tags or [])


def map_block(here: Path, lat, lon, name, precision, prefix=""):
    lid = "map"
    z = zoom_for(precision)
    tiles = rel(here, DOCS / "tiles")
    vendor_js = rel(here, VENDOR / "leaflet.js")
    vendor_css = rel(here, VENDOR / "leaflet.css")
    g, geo = maps_links(lat, lon, name)
    extra_head = f'<link rel="stylesheet" href="{vendor_css}">'
    extra_js = f"""<script src="{vendor_js}"></script>
<script>
(function() {{
  var map = L.map('{lid}', {{zoomControl: true}}).setView([{lat}, {lon}], {z});
  L.tileLayer('{tiles}/{{z}}/{{x}}/{{y}}.jpg', {{
    maxZoom: 16, minZoom: 12,
    errorTileUrl: 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==',
    attribution: 'Tiles © Esri, HERE, Garmin, © OpenStreetMap contributors'
  }}).addTo(map);
  L.marker([{lat}, {lon}]).addTo(map).bindPopup({json.dumps(name)});
}})();
</script>"""
    html = f"""<div id="{lid}" class="map"></div>
<p class="map-actions">
  <a class="btn" href="{esc(g)}">Open in Google Maps</a>
  <a class="btn ghost" href="{esc(geo)}">geo:</a>
</p>"""
    return html, extra_head, extra_js


APP_CSS = """
:root {
  --bg: #1c120c;
  --bg2: #2a1b14;
  --card: #342218;
  --text: #f4e8d8;
  --muted: #c4b09a;
  --accent: #e07a3d;
  --accent2: #f0c36a;
  --line: #4a3428;
  --ok: #7dce82;
  --radius: 14px;
  --nav-h: 64px;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text);
  font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 430px; margin: 0 auto; padding: 16px 16px calc(var(--nav-h) + 20px); }
h1 { font-size: 1.45rem; margin: 0 0 8px; }
h2 { font-size: 1.15rem; margin: 20px 0 8px; }
h3 { font-size: 1rem; margin: 0 0 6px; }
p { margin: 0 0 10px; }
a { color: var(--accent2); }
.muted { color: var(--muted); font-size: 0.92rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 14px; margin: 0 0 12px; }
.card.today { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.hero { width: 100%; height: 140px; object-fit: cover; border-radius: var(--radius); margin-bottom: 12px; display: block; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.badge { display: inline-block; background: var(--bg2); border: 1px solid var(--line);
  color: var(--accent2); padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; }
.badge.free { background: #3a2a12; color: var(--accent); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: 44px;
  padding: 10px 14px; background: var(--accent); color: #1c120c; font-weight: 700;
  text-decoration: none; border-radius: 10px; border: 0; font-size: 0.95rem; }
.btn.ghost { background: transparent; color: var(--accent2); border: 1px solid var(--line); }
.btn + .btn { margin-left: 0; }
.map-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.timeline { list-style: none; padding: 0; margin: 0 0 12px; border-left: 2px solid var(--line); }
.timeline li { padding: 0 0 12px 14px; position: relative; }
.timeline li::before { content: ""; width: 8px; height: 8px; background: var(--accent);
  border-radius: 50%; position: absolute; left: -5px; top: 6px; }
.bottom-nav { position: fixed; left: 0; right: 0; bottom: 0; height: var(--nav-h);
  background: var(--bg2); border-top: 1px solid var(--line); display: flex;
  justify-content: space-around; align-items: stretch; z-index: 20;
  padding-bottom: env(safe-area-inset-bottom); }
.bottom-nav a { flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--muted); text-decoration: none; font-size: 0.78rem; font-weight: 600; min-height: 44px; }
.bottom-nav a.active { color: var(--accent); }
.pill { position: fixed; top: 8px; right: 8px; z-index: 30; background: var(--bg2);
  border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; font-size: 0.75rem; color: var(--ok); }
.check { display: flex; gap: 10px; align-items: flex-start; margin: 8px 0; min-height: 44px; }
.check input { width: 22px; height: 22px; margin-top: 2px; flex-shrink: 0; }
textarea { width: 100%; min-height: 90px; background: var(--bg); color: var(--text);
  border: 1px solid var(--line); border-radius: 10px; padding: 10px; font: inherit; }
.day-link { display: flex; justify-content: space-between; gap: 8px; margin: 16px 0; }
.map { height: 260px; width: 100%; border-radius: var(--radius); background: var(--bg2); margin: 8px 0; }
.leaflet-container { background: var(--bg2); }
ul.plain { padding-left: 1.1rem; }
"""

APP_JS = r"""
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
    navigator.serviceWorker.register(swUrl).then(() => {
      const pill = document.getElementById("offline-pill");
      if (pill) {
        pill.textContent = navigator.onLine ? "offline ready ✓" : "offline ready ✓";
      }
    }).catch(() => {
      const pill = document.getElementById("offline-pill");
      if (pill) pill.textContent = "sw failed";
    });
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      const pill = document.getElementById("offline-pill");
      if (pill) pill.textContent = "updating…";
    });
  }
})();
"""


def sw_js(version: str) -> str:
    return f"""
const CACHE = "peru-2027-{version}";
self.addEventListener("install", event => {{
  event.waitUntil(
    fetch("precache.json").then(r => r.json()).then(files =>
      caches.open(CACHE).then(c => c.addAll(files))
    ).then(() => self.skipWaiting())
  );
}});
self.addEventListener("activate", event => {{
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim())
  );
}});
self.addEventListener("fetch", event => {{
  const req = event.request;
  if (req.method !== "GET") return;
  event.respondWith(
    caches.match(req).then(cached => {{
      if (cached) return cached;
      return fetch(req).then(res => {{
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {{}});
        return res;
      }}).catch(() => cached);
    }})
  );
}});
"""


def write_manifest():
    (DOCS / "manifest.webmanifest").write_text(json.dumps({
        "name": "Peru 2027",
        "short_name": "Peru 2027",
        "start_url": "./index.html",
        "display": "standalone",
        "background_color": "#1c120c",
        "theme_color": "#1c120c",
        "icons": [
            {"src": "img/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "img/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }, indent=2), encoding="utf-8")


def generate_pages(trip, pins):
    hotels = {h["id"]: h for h in trip["hotels"]}
    pinmap = pins.get("pins", pins) if isinstance(pins, dict) else {}

    days_json = []
    for d in trip["days"]:
        h = hotels.get(d.get("hotel") or "")
        days_json.append({
            "n": d["n"], "date": d["date"], "title": d["title"],
            "altitude_m": d["altitude_m"], "free": d.get("free") or [],
            "hotelName": h["name"] if h else None,
        })
    photo_slots = [s["name"] for s in trip["sites"] if s.get("photo_slot")]

    # index
    here = DOCS / "index.html"
    day_cards = []
    for d in trip["days"]:
        h = hotels.get(d.get("hotel") or "")
        free_badge = '<span class="badge free">free time</span>' if d.get("free") else ""
        href = f'day/{d["n"]:02d}.html'
        day_cards.append(f"""<a class="card" href="{href}" style="display:block;text-decoration:none;color:inherit">
          <div class="row"><strong>Day {d["n"]}</strong> <span class="muted">{esc(d["date"])}</span> {free_badge}</div>
          <h3>{esc(d["title"])}</h3>
          <p class="muted">{esc(h["name"] if h else "in transit")} · {d["altitude_m"]} m</p>
        </a>""")
    hero = ""
    for name in ["albatros-p02-1.jpg", "albatros-p02-2.jpg", "albatros-p03-1.jpg"]:
        p = DOCS / "img" / name
        if p.exists():
            hero = f'<img class="hero" src="img/{name}" alt="Peru tour photo">'
            break
    body = f"""
<div id="offline-pill" class="pill">updating…</div>
{hero}
<h1>{esc(trip["trip"]["title"])}</h1>
<p class="muted">{esc(trip["trip"].get("subtitle",""))} · {trip["trip"]["start"]} – {trip["trip"]["end"]}</p>
<script type="application/json" id="trip-days-json">{json.dumps(days_json)}</script>
<script type="application/json" id="trip-photo-slots-json">{json.dumps(photo_slots)}</script>
<div data-today-card></div>
<h2 id="days">Days</h2>
{''.join(day_cards)}
<p><a href="packing.html">Packing</a> · <a href="sites.html">All sites</a></p>
<script>
window.TRIP_TZ = {json.dumps(trip["trip"]["tz"])};
window.TRIP_START = {json.dumps(trip["trip"]["start"])};
window.TRIP_END = {json.dumps(trip["trip"]["end"])};
</script>
"""
    here.write_text(page_shell(here, "Peru 2027", body, active="today"), encoding="utf-8")

    # days
    (DOCS / "day").mkdir(exist_ok=True)
    ndays = len(trip["days"])
    for d in trip["days"]:
        here = DOCS / "day" / f"{d['n']:02d}.html"
        h = hotels.get(d.get("hotel") or "")
        prog = "".join(f"<li>{esc(p)}</li>" for p in d.get("programme") or [])
        free = "".join(f"<p><strong>{esc(f.get('from',''))}</strong> — {esc(f.get('note',''))}</p>" for f in d.get("free") or [])
        tcards = []
        for slug in d.get("targets") or []:
            s = site_by_slug(trip, slug)
            if not s:
                continue
            g, geo = maps_links(s["lat"], s["lon"], s["name"])
            det = rel(here, DOCS / "site" / f"{s['slug']}.html")
            tcards.append(f"""<div class="card">
              <h3>{esc(s["name"])}</h3>
              <p>{tag_badges(s.get("tags"))}</p>
              <p class="muted">{esc(s.get("from_hotel",""))}</p>
              <p class="muted">{esc(s.get("hours",""))} · {esc(s.get("ticket",""))}</p>
              <p class="map-actions">
                <a class="btn" href="{esc(g)}">Open in Google Maps</a>
                <a class="btn ghost" href="{det}">Details</a>
              </p>
            </div>""")
        prevn = d["n"] - 1
        nextn = d["n"] + 1
        prev = f'<a class="btn ghost" href="{prevn:02d}.html">← Day {prevn}</a>' if prevn >= 1 else "<span></span>"
        nxt = f'<a class="btn ghost" href="{nextn:02d}.html">Day {nextn} →</a>' if nextn <= ndays else "<span></span>"
        hotel_line = esc(h["name"] + " · " + h["city"]) if h else "in transit"
        body = f"""
<p class="muted"><a href="{rel(here, DOCS / "index.html")}">← Days</a></p>
<h1>Day {d["n"]} · {esc(d["title"])}</h1>
<p class="muted">{esc(d["date"])} · {hotel_line} · {d["altitude_m"]} m · meals {esc(d.get("meals","—"))}</p>
<h2>Programme</h2>
<ul class="timeline">{prog}</ul>
<h2>Free time</h2>
<div class="card">{free or "<p class='muted'>None listed</p>"}</div>
<h2>Targets</h2>
{''.join(tcards) or "<p class='muted'>No rabbit-hole targets this day.</p>"}
<div class="day-link">{prev}{nxt}</div>
"""
        here.write_text(page_shell(here, f"Day {d['n']} · Peru 2027", body, active="days"), encoding="utf-8")

    # sites index + pages
    (DOCS / "site").mkdir(exist_ok=True)
    here = DOCS / "sites.html"
    cards = []
    for s in trip["sites"]:
        href = rel(here, DOCS / "site" / f"{s['slug']}.html")
        cards.append(f"""<a class="card" href="{href}" style="display:block;text-decoration:none;color:inherit">
          <h3>{esc(s["name"])}</h3>
          <p>{tag_badges(s.get("tags"))}</p>
          <p class="muted">{esc(s.get("from_hotel",""))}</p>
        </a>""")
    here.write_text(page_shell(here, "Sites · Peru 2027", f"<h1>Sites</h1>{''.join(cards)}", active="sites"), encoding="utf-8")

    for s in trip["sites"]:
        here = DOCS / "site" / f"{s['slug']}.html"
        mmap, extra_head, extra_js = map_block(here, s["lat"], s["lon"], s["name"], s.get("precision"))
        pin_html = ""
        pid = s.get("encyclopedia_pin")
        pin = pinmap.get(pid) if pid else None
        if pin:
            claims = "".join(f"<li>{esc(c)}</li>" for c in pin.get("claims") or [])
            srcs = "".join(f'<li><a href="{esc(x["url"])}">{esc(x["label"])}</a></li>' for x in pin.get("sources") or [])
            pin_html = f"""<h2>From the encyclopedia</h2>
            <div class="card">
              <p>{esc(pin.get("summary",""))}</p>
              <h3>Claims</h3>
              <ul class="plain">{claims}</ul>
              <h3>Sources</h3>
              <ul class="plain">{srcs}</ul>
            </div>"""
        src_urls = "".join(f'<li><a href="{esc(u)}">{esc(u)}</a></li>' for u in s.get("source_urls") or [])
        look = json.dumps(s.get("look_for") or [])
        body = f"""
<p class="muted"><a href="{rel(here, DOCS / "sites.html")}">← Sites</a></p>
<h1>{esc(s["name"])}</h1>
<p>{tag_badges(s.get("tags"))} <span class="badge">{esc(s.get("precision","approx"))}</span></p>
<h2>What it is</h2>
<p>{esc(s.get("what",""))}</p>
<h2>Look for</h2>
<div data-look-for="{esc(s["slug"])}" data-items='{esc(look)}'></div>
<p class="muted">{esc(s.get("from_hotel",""))}</p>
<p><strong>Hours:</strong> {esc(s.get("hours",""))}<br>
<strong>Ticket:</strong> {esc(s.get("ticket",""))}</p>
{f'<ul class="plain">{src_urls}</ul>' if src_urls else ""}
{mmap}
{pin_html}
<h2>My notes</h2>
<textarea data-notes="{esc(s["slug"])}" placeholder="Notes stay on this phone"></textarea>
"""
        here.write_text(page_shell(here, s["name"] + " · Peru 2027", body, extra_head=extra_head, extra_js=extra_js, active="sites"), encoding="utf-8")

    # hotels
    here = DOCS / "hotels.html"
    blocks = []
    extra_heads = []
    extra_jss = []
    for i, h in enumerate(trip["hotels"]):
        hid = f"map-{h['id']}"
        # reuse map_block but unique id — patch
        html, eh, ej = map_block(here, h["lat"], h["lon"], h["name"], h.get("precision", "approx"))
        html = html.replace('id="map"', f'id="{hid}"')
        ej = ej.replace("'map'", f"'{hid}'")
        g, geo = maps_links(h["lat"], h["lon"], h["name"])
        extra_heads.append(eh)
        extra_jss.append(ej)
        blocks.append(f"""<div class="card">
          <h2>{esc(h["name"])}</h2>
          <p>{esc(h["city"])} · {esc(h["nights"])}</p>
          <p>{esc(h["address"])}</p>
          <p>{esc(h.get("phone") or "phone: update when documents arrive")}</p>
          <p class="muted">{esc(h.get("note",""))}</p>
          {html}
        </div>""")
    eh = extra_heads[0] if extra_heads else ""
    here.write_text(page_shell(here, "Hotels · Peru 2027", "<h1>Hotels</h1>" + "".join(blocks), extra_head=eh, extra_js="\n".join(extra_jss), active="hotels"), encoding="utf-8")

    # contacts
    here = DOCS / "contacts.html"
    ag = trip["trip"]["agency"]
    c = trip["contacts"]
    body = f"""
<h1>Contacts</h1>
<div class="card">
  <h2>{esc(ag["name"])}</h2>
  <p><a href="tel:{esc(ag["phone"])}">{esc(ag["phone"])}</a><br>
  <a href="mailto:{esc(ag["email"])}">{esc(ag["email"])}</a></p>
  <p>Booking {esc(ag["booking"])} · member {esc(ag.get("member",""))}</p>
  <p><a href="{esc(ag["portal"])}">{esc(ag["portal"])}</a></p>
  <p class="muted">{esc(ag.get("hours",""))}</p>
</div>
<div class="card">
  <h2>Tour leader</h2>
  <p>{esc(c["tour_leader"]["name"])}</p>
  <p class="muted">{esc(c["tour_leader"]["note"])}</p>
</div>
<div class="card">
  <h2>Embassy</h2>
  <p>{esc(c["embassy"]["name"])}</p>
  <p class="muted">{esc(c["embassy"]["note"])}</p>
</div>
<div class="card">
  <h2>Emergency</h2>
  <p>Police {esc(c["emergency"]["police"])} · Ambulance {esc(c["emergency"]["ambulance"])}</p>
  <p class="muted">{esc(c["emergency"]["note"])}</p>
</div>
<div class="card">
  <h2>Insurance</h2>
  <p class="muted">{esc(c["insurance"]["note"])}</p>
</div>
<p><a href="packing.html">Packing list</a></p>
"""
    here.write_text(page_shell(here, "Contacts · Peru 2027", body, active="contacts"), encoding="utf-8")

    # packing
    here = DOCS / "packing.html"
    pack = "".join(f"<li>{esc(x)}</li>" for x in trip.get("packing") or [])
    prac = "".join(f"<li>{esc(x)}</li>" for x in trip.get("practical") or [])
    body = f"<h1>Packing</h1><ul class='plain'>{pack}</ul><h2>Practical</h2><ul class='plain'>{prac}</ul>"
    here.write_text(page_shell(here, "Packing · Peru 2027", body, active="contacts"), encoding="utf-8")


def deg2num(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def tile_box(lat, lon, zoom, km=1.0):
    # degrees for ~km
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    x0, y0 = deg2num(lat + dlat, lon - dlon, zoom)
    x1, y1 = deg2num(lat - dlat, lon + dlon, zoom)
    xs = range(min(x0, x1), max(x0, x1) + 1)
    ys = range(min(y0, y1), max(y0, y1) + 1)
    return [(x, y) for x in xs for y in ys]


def download_tiles(trip, rate=4.0):
    points = []
    for h in trip["hotels"]:
        points.append((h["lat"], h["lon"]))
    for s in trip["sites"]:
        points.append((s["lat"], s["lon"]))
    needed = set()
    for lat, lon in points:
        for z in range(12, 17):
            for x, y in tile_box(lat, lon, z, km=1.0):
                needed.add((z, x, y))
    delay = 1.0 / rate
    n_new = 0
    n_skip = 0
    bytes_ = 0
    for i, (z, x, y) in enumerate(sorted(needed)):
        dest = DOCS / "tiles" / str(z) / str(x) / f"{y}.jpg"
        if dest.exists() and dest.stat().st_size > 0:
            n_skip += 1
            bytes_ += dest.stat().st_size
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = TILE_TMPL.format(z=z, y=y, x=x)
        try:
            urllib.request.urlretrieve(url, dest)
            n_new += 1
            bytes_ += dest.stat().st_size
        except Exception as e:
            print("tile fail", url, e)
        time.sleep(delay)
        if (i + 1) % 50 == 0:
            print(f"  tiles {i+1}/{len(needed)}")
    mb = bytes_ / (1024 * 1024)
    print(f"Tiles: {len(needed)} unique, {n_new} downloaded, {n_skip} skipped, {mb:.1f} MB")
    return len(needed), mb


def write_precache():
    files = []
    for p in DOCS.rglob("*"):
        if not p.is_file():
            continue
        if p.name == "precache.json":
            continue
        relp = "./" + p.relative_to(DOCS).as_posix()
        files.append(relp)
    files.sort()
    (DOCS / "precache.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", action="store_true")
    args = ap.parse_args()
    trip = json.loads(DATA.read_text(encoding="utf-8"))
    pins = json.loads(PINS.read_text(encoding="utf-8")) if PINS.exists() else {}
    ver = cache_version(trip)
    print("CACHE_VERSION", ver)
    DOCS.mkdir(exist_ok=True)
    ensure_leaflet()
    write_png(DOCS / "img" / "icon-192.png", 192, 192)
    write_png(DOCS / "img" / "icon-512.png", 512, 512)
    (DOCS / "app.css").write_text(APP_CSS, encoding="utf-8")
    (DOCS / "app.js").write_text(APP_JS, encoding="utf-8")
    write_manifest()
    generate_pages(trip, pins)
    if args.tiles:
        download_tiles(trip)
    else:
        print("Skipping tiles (pass --tiles)")
        (DOCS / "tiles").mkdir(exist_ok=True)
    files = write_precache()
    (DOCS / "sw.js").write_text(sw_js(ver), encoding="utf-8")
    # rewrite precache to include sw + precache itself? sw fetches precache.json
    files = write_precache()
    print(f"Wrote {len(files)} files into precache.json")
    print("OK", DOCS / "index.html")


if __name__ == "__main__":
    main()
