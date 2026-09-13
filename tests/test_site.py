"""Smoke tests for the Peru 2027 static PWA."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_build_and_precache():
    r = subprocess.run([sys.executable, str(ROOT / "build.py")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (DOCS / "index.html").exists()
    listed = set(json.loads((DOCS / "precache.json").read_text(encoding="utf-8")))
    files = []
    for p in DOCS.rglob("*"):
        if p.is_file() and p.name != "precache.json":
            files.append("./" + p.relative_to(DOCS).as_posix())
    missing = set(files) - listed
    extra = listed - set(files)
    assert not missing, f"precache missing {list(missing)[:10]}"
    assert not extra, f"precache extra {list(extra)[:10]}"


def test_no_remote_assets():
    import re
    for p in list(DOCS.rglob("*.html")) + list(DOCS.rglob("*.css")) + list(DOCS.rglob("*.js")):
        if p.name == "precache.json":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"""<(?:link|script)[^>]+(?:href|src)=['"]([^'"]+)['"]""", text, re.I):
            src = m.group(1)
            if src.startswith("data:"):
                continue
            assert not src.startswith("http://") and not src.startswith("https://"), f"{p}: {src}"


@pytest.mark.skipif(os.environ.get("SKIP_PLAYWRIGHT") == "1", reason="skip playwright")
def test_playwright_suite():
    playwright = pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    import threading
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(DOCS), **k)

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            for html in sorted((DOCS / "day").glob("*.html")):
                page.goto(f"{base}/day/{html.name}", wait_until="load")
                assert not errors, errors
            errors.clear()
            for html in sorted((DOCS / "site").glob("*.html")):
                page.goto(f"{base}/site/{html.name}", wait_until="load")
                assert not errors, f"{html.name}: {errors}"
            errors.clear()

            page.goto(f"{base}/index.html?day=7", wait_until="load")
            page.wait_for_selector("#today-card", timeout=5000)
            card = page.locator("#today-card")
            assert card.count() == 1
            assert "Day 7" in card.inner_text()

            # pick a site with a map
            page.goto(f"{base}/site/sacsayhuaman.html", wait_until="networkidle")
            imgs = page.locator(".leaflet-tile-pane img")
            assert imgs.count() >= 1
            src = imgs.first.get_attribute("src") or ""
            assert "/tiles/" in src or "tiles/" in src
            assert "http://server.arcgisonline" not in src and "https://server.arcgisonline" not in src

            page.goto(f"{base}/index.html", wait_until="networkidle")
            page.wait_for_function(
                "document.getElementById('offline-pill')?.textContent.includes('offline ready')",
                timeout=120000,
            )
            page.goto(f"{base}/day/06.html", wait_until="networkidle")
            context.set_offline(True)
            page.reload(wait_until="load")
            assert page.locator("h1").count() >= 1
            assert "Machu" in page.locator("h1").inner_text() or "Day 6" in page.locator("h1").inner_text()
            context.set_offline(False)
            browser.close()
    finally:
        httpd.shutdown()
