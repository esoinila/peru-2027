# Peru 2027 — offline trip PWA

## 📱 LIVE SITE → **https://esoinila.github.io/peru-2027/**

Open that link on your phone (on wifi), Chrome menu → **Add to Home screen**, wait for **offline ready ✓**.

---

Static site + PWA for the Albatros tour **Inkojen aarteet ja aromit** (PESGL15AFI), 4–17 Mar 2027. GitHub Pages serves `docs/` from `main`. Install once on wifi, then use offline in Peru.

Source of truth: `data/trip.json` (transcribed from the private itinerary / rabbit-holes / booking files — the agency PDF is **not** in this repo).

## Rebuild

```bash
python build.py           # HTML/CSS/JS/icons only
python build.py --tiles   # also download Esri World Street Map tiles (zooms 12–16, ~1 km around each site/hotel)
```

Requires Python 3.11+ stdlib. First `--tiles` run is slow (≤4 req/s). Skip existing tile files. Target ≤ 60 MB of tiles.

Leaflet 1.9.4 is vendored into `docs/vendor/` at build time (not CDN at runtime).

Last tile build: **1149 tiles, 14.8 MB** (zooms 12–16, ~1 km boxes).

## Install on Android

1. Open the GitHub Pages URL on **wifi**.
2. Chrome → menu → **Add to Home screen**.
3. Wait until the index pill says **offline ready ✓**.
4. Airplane mode: Today card, day 6, and a site map inset should still work.

## Hotel confirmations (~25 Feb 2027)

When Albatros sends travel documents, edit `data/trip.json`:

- `hotels[].name`, `address`, `phone`, `lat`, `lon`
- `contacts.tour_leader`
- `contacts.insurance`

Then `python build.py` (re-run `--tiles` only if coordinates changed) and push `docs/`.

## Tests

```bash
pip install pytest playwright
playwright install chromium
pytest -q
```

CI runs pytest and skips Playwright if it is not installed (`SKIP_PLAYWRIGHT=1` or import skip). CI does **not** run `build.py` (tiles are committed).

## Pages

- `docs/index.html` — today card + 14 day cards
- `docs/day/01.html` … `14.html`
- `docs/site/<slug>.html`
- `docs/hotels.html`, `contacts.html`, `packing.html`

Hours and ticket prices not in the source notes are marked **unverified — check on site**. Encyclopedia pin coordinates are copied verbatim from `data/globe-pins-peru.json`. Other coordinates are approximate (hotel/site neighbourhoods) until documents arrive.
