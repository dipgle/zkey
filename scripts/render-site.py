#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render site/index.html in a real WebKit view on a private display; screenshot.

Run with ZKEY_TEST_DISPLAY (private Xvfb). Writes .tmp/site-<width>.png for
desktop (1280) and phone (390) widths and fails if the page reports a
JavaScript/console error, loads anything from the network, or overflows
horizontally. Exit 0 pass, 1 fail, 2 not measurable; ends GATE_EXIT.
"""
from pathlib import Path
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402  (never dbus-run-session directly)
PAGE = ROOT / "site/index.html"


def inside():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import GLib, Gtk, WebKit2
    if not Gtk.init_check([])[0]:
        print("NOT_MEASURABLE: no display")
        return 2
    problems = []
    for width, height in ((1280, 900), (390, 844)):
        window = Gtk.OffscreenWindow()
        view = WebKit2.WebView()
        view.set_size_request(width, height)
        window.add(view)
        window.show_all()
        requests = []
        view.connect("resource-load-started", lambda _v, _r, request: requests.append(request.get_uri()))
        loop = GLib.MainLoop()
        view.connect("load-changed", lambda _v, event: loop.quit() if event == WebKit2.LoadEvent.FINISHED else None)
        view.load_uri(PAGE.as_uri())
        GLib.timeout_add_seconds(15, loop.quit)
        loop.run()
        result = {}
        script = ("JSON.stringify({w: document.documentElement.scrollWidth, vw: innerWidth, "
                  "h: document.documentElement.scrollHeight, title: document.title})")
        done = GLib.MainLoop()

        def finished(webview, task):
            try:
                value = webview.evaluate_javascript_finish(task)
                result.update(__import__("json").loads(value.to_string()))
            except GLib.Error as error:
                problems.append(f"{width}: script error {error.message}")
            done.quit()
        view.evaluate_javascript(script, -1, None, None, None, finished)
        done.run()
        external = [uri for uri in requests if not uri.startswith(("file://", "data:"))]
        if external:
            problems.append(f"{width}: network requests {external}")
        if result.get("w", 0) > result.get("vw", width) + 1:
            problems.append(f"{width}: horizontal overflow {result.get('w')} > {result.get('vw')}")
        # Full-page capture: grow the view to the document height, then snapshot.
        view.set_size_request(width, min(int(result.get("h", height)), 6000))
        until = time.monotonic() + 1.5
        while time.monotonic() < until:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            time.sleep(0.01)
        pixbuf = window.get_pixbuf()
        out = ROOT / f".tmp/site-{width}.png"
        if pixbuf is None:
            problems.append(f"{width}: no snapshot")
        else:
            pixbuf.savev(str(out), "png", [], [])
        print(f"RENDER {width}px: title={result.get('title')!r} height={result.get('h')} "
              f"requests={len(requests)} external={len(external)} -> {out}")
        window.destroy()
    if problems:
        print("SITE FAILED: " + " | ".join(problems))
        return 1
    print("PASS site: renders at 1280 and 390 px, no external requests, no horizontal overflow.")
    return 0


def main():
    if sys.argv[1:] == ["--inside"]:
        return inside()
    display = os.environ.get("ZKEY_TEST_DISPLAY")
    if not display or not PAGE.exists():
        print("NOT_MEASURABLE: needs ZKEY_TEST_DISPLAY (private Xvfb) and site/index.html")
        return 2
    env = dict(os.environ, DISPLAY=display, GDK_BACKEND="x11", NO_AT_BRIDGE="1", GIO_USE_VFS="local",
               WEBKIT_DISABLE_COMPOSITING_MODE="1")
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), "--inside"], env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
