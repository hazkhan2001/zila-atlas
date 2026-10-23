"""
check_site.py: open the website in a headless browser and screenshot each view.

    python tests/check_site.py [output_folder]

Serves site/ locally, answers requests for the CDN libraries from local
copies (set LIB_DIR), and reports any console errors.
"""

import http.server
import os
import sys
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "screens"
LIB = Path(os.environ.get("LIB_DIR", "/home/claude/npmtmp"))
LIBS = {
    "d3.min.js": LIB / "d3" / "dist" / "d3.min.js",
    "maplibre-gl.js": LIB / "maplibre" / "dist" / "maplibre-gl.js",
}


def serve():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srv = serve()
    base = f"http://127.0.0.1:{srv.server_port}/index.html"
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        for scheme in ["light", "dark"]:
            for width, height, tag in [(1400, 900, "desktop"), (400, 860, "phone")]:
                page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=scheme)
                page.on("console", lambda m: m.type == "error" and errors.append(f"{tag}/{scheme}: {m.text}"))
                page.on("pageerror", lambda e: errors.append(f"{tag}/{scheme} PAGEERROR: {e}"))

                def route(r):
                    name = r.request.url.rsplit("/", 1)[-1]
                    if name in LIBS:
                        return r.fulfill(path=str(LIBS[name]), content_type="application/javascript")
                    return r.abort()
                page.route("https://cdnjs.cloudflare.com/**", route)
                page.route("https://fonts.googleapis.com/**", lambda r: r.abort())
                page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
                page.route("https://server.arcgisonline.com/**", lambda r: r.abort())

                for view in ["PB-LAHORE", "compare", "firms", "economy", "data", "JK-MUZAFFARABAD"]:
                    page.goto(f"{base}#{view}")
                    page.wait_for_timeout(2500)
                    full = view not in ("PB-LAHORE", "JK-MUZAFFARABAD") or tag == "phone"
                    page.screenshot(path=str(OUT / f"{tag}-{scheme}-{view}.png"), full_page=full)
                overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                if overflow:
                    errors.append(f"{tag}/{scheme}: page scrolls horizontally")
                page.close()
        browser.close()
    srv.shutdown()
    benign = ("ERR_FAILED", "ERR_BLOCKED", "net::", "Failed to load resource", "AJAXError")
    real = [e for e in errors if not any(b in e for b in benign)]
    print(f"screenshots in {OUT}")
    print("\n".join(real) if real else "no console errors")


if __name__ == "__main__":
    main()
