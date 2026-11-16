#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small real-browser driver (WebKit2) for UI work a person would do by hand.

Runs on a private display (ZKEY_TEST_DISPLAY) + private D-Bus, keeps ONE
browser page alive and takes commands from .tmp/web-driver/cmd.json:
  {"id": n, "op": "open", "url": ...}          first page only
  {"id": n, "op": "click", "selector": css}     real pointer click (XTest) at the element
  {"id": n, "op": "type", "text": ...}          real key presses (XTest) into the focused field
  {"id": n, "op": "key", "name": "Return"}      one real key
  {"id": n, "op": "upload", "selector": css, "path": file}  answer the file chooser it opens
  {"id": n, "op": "look"}                       screenshot + visible text + controls
  {"id": n, "op": "quit"}
Each result: .tmp/web-driver/out-<n>.json + shot-<n>.png. Reading the page
(look) uses JavaScript to LIST what is shown; actions are real input events.
Cookies live in .tmp/web-driver/profile (not the user's browser).
"""
from pathlib import Path
import ctypes as C
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402
import verify_site  # noqa: E402
DIR = ROOT / ".tmp/web-driver"
LOOK = r"""(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const css = e => { if (e.id) return '#' + CSS.escape(e.id);
    const p = []; for (let n = e; n && n.nodeType === 1 && p.length < 6; n = n.parentElement) {
      let s = n.tagName.toLowerCase(); const sib = n.parentElement ? [...n.parentElement.children].filter(c => c.tagName === n.tagName) : [];
      if (sib.length > 1) s += ':nth-of-type(' + (sib.indexOf(n) + 1) + ')'; p.unshift(s); if (n.id) { p[0] = '#' + CSS.escape(n.id); break; } }
    return p.join(' > '); };
  const controls = [...document.querySelectorAll('a,button,input,select,textarea,[role=button],[role=tab],[role=menuitem],label')]
    .filter(vis).slice(0, 150).map(e => ({tag: e.tagName.toLowerCase(), type: e.type || '', text: (e.innerText || e.value || e.placeholder || e.getAttribute('aria-label') || '').trim().slice(0, 60), sel: css(e)}));
  const imgs = [...document.querySelectorAll('img,canvas,svg')].filter(vis).slice(0, 20).map(e => ({tag: e.tagName.toLowerCase(), alt: e.alt || '', sel: css(e), w: e.getBoundingClientRect().width|0}));
  return JSON.stringify({url: location.href, title: document.title, text: document.body ? document.body.innerText.slice(0, 3000) : '', controls, imgs});
})()"""


def inside():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkX11", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, GdkX11, GLib, Gtk, WebKit2
    if not Gtk.init_check([])[0]:
        print("NOT_MEASURABLE: no display", flush=True)
        return 2
    DIR.mkdir(parents=True, exist_ok=True)
    verify = sys.argv[2:] == ["--verify-site"]
    if verify:
        # Public verification never reuses the Studio login profile.
        context = WebKit2.WebContext.new_ephemeral()
    else:
        profile = DIR / "profile"
        manager = WebKit2.WebsiteDataManager(base_data_directory=str(profile / "data"),
                                             base_cache_directory=str(profile / "cache"))
        context = WebKit2.WebContext.new_with_website_data_manager(manager)
        cookies = manager.get_cookie_manager()
        cookies.set_persistent_storage(str(profile / "cookies.sqlite"), WebKit2.CookiePersistentStorage.SQLITE)
    view = WebKit2.WebView.new_with_context(context)
    window = Gtk.Window(title="zkey web-driver")
    window.set_default_size(1280, 900)
    window.add(view)
    window.show_all()
    pending_file = {"path": None}

    def on_file_chooser(_view, request):
        if pending_file["path"]:
            request.select_files([pending_file["path"]])
            pending_file["path"] = None
            return True
        return False
    view.connect("run-file-chooser", on_file_chooser)
    main = GLib.MainContext.default()

    def pump(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            while main.pending():
                main.iteration(False)
            time.sleep(0.01)

    def js(source):
        box = {}
        loop = GLib.MainLoop()

        def done(webview, task):
            try:
                box["v"] = webview.evaluate_javascript_finish(task).to_string()
            except GLib.Error as error:
                box["e"] = error.message
            loop.quit()
        view.evaluate_javascript(source, -1, None, None, None, done)
        def timed_out():
            box["e"] = "browser JavaScript evaluation timed out"
            loop.quit()
            return GLib.SOURCE_REMOVE
        timeout = GLib.timeout_add_seconds(10, timed_out)
        loop.run()
        if "v" in box or box.get("e") != "browser JavaScript evaluation timed out":
            GLib.source_remove(timeout)
        if "e" in box:
            raise RuntimeError(box["e"])
        if "v" not in box:
            raise RuntimeError("browser JavaScript evaluation timed out")
        return box["v"]

    if verify:
        # Fixed public target explicitly assigned in the handoff; read-only.
        url = "https://zkey.dipgle.com/"
        result = {"requested_url": url}
        errors = []
        finished = []
        view.connect("load-failed", lambda _v, _event, _uri, error: errors.append(error.message) or False)
        view.connect("load-changed", lambda _v, event: finished.append(True)
                     if event == WebKit2.LoadEvent.FINISHED else None)
        view.load_uri(url)
        deadline = time.monotonic() + 45
        while not finished and not errors and time.monotonic() < deadline:
            pump(0.1)
        code = 2
        try:
            if errors or not finished or view.get_uri() != url:
                raise RuntimeError(f"page load unavailable/redirected: {errors}, uri={view.get_uri()}")
            result["page"] = json.loads(js(LOOK))
            js(verify_site.BROWSER_READ)
            deadline = time.monotonic() + 30
            observation = {"pending": True}
            while observation.get("pending") and time.monotonic() < deadline:
                pump(0.1)
                observation = json.loads(js("JSON.stringify(window.__zkeySiteBytes)"))
            expected = (ROOT / "site/index.html").read_bytes()
            code, reason = verify_site.compare(observation, expected, url)
            control, _ = verify_site.compare(observation, expected + b"\n", url)
            result.update(observation=observation, expected_size=len(expected), reason=reason,
                          negative_control_exit=control)
            if code == 0 and control != 1:
                code = 1
                result["reason"] = "negative control did not reject altered source bytes"
        except (RuntimeError, ValueError, OSError) as error:
            result["error"] = str(error)
        result["exit"] = code
        out = ROOT / ".tmp/site-verification.json"
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        window.destroy()
        return code

    x = C.CDLL("libX11.so.6")
    t = C.CDLL("libXtst.so.6")
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
    x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
    x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
    x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
    x.XFlush.argtypes = [C.c_void_p]
    x.XSync.argtypes = [C.c_void_p, C.c_int]
    t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
    t.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]
    t.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
    display = x.XOpenDisplay(os.environ["DISPLAY"].encode())
    pump(0.5)
    x.XSetInputFocus(display, GdkX11.X11Window.get_xid(window.get_window()), 2, 0)
    x.XSync(display, False)

    def key(name, shift=False):
        code = x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode()))
        if not code:
            raise RuntimeError(f"no keycode for {name!r}")
        sh = x.XKeysymToKeycode(display, x.XStringToKeysym(b"Shift_L"))
        if shift:
            t.XTestFakeKeyEvent(display, sh, True, 0)
        t.XTestFakeKeyEvent(display, code, True, 0)
        t.XTestFakeKeyEvent(display, code, False, 0)
        if shift:
            t.XTestFakeKeyEvent(display, sh, False, 0)
        x.XFlush(display)
        pump(0.03)

    names = {" ": "space", "@": ("at", True), ".": "period", "-": "minus", "_": ("underscore", True), "/": "slash",
             ":": ("colon", True)}

    def type_text(text):
        for ch in text:
            spec = names.get(ch, ch)
            name, shift = (spec if isinstance(spec, tuple) else (spec, ch.isupper()))
            key(name.lower() if len(name) == 1 else name, shift)

    def click(selector):
        rect = json.loads(js("(() => { const e = document.querySelector(%s); if (!e) return 'null'; e.scrollIntoView({block:'center'});"
                             " const r = e.getBoundingClientRect(); return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2}); })()"
                             % json.dumps(selector)))
        if rect is None:
            raise RuntimeError(f"no element {selector}")
        pump(0.2)
        rect = json.loads(js("(() => { const r = document.querySelector(%s).getBoundingClientRect();"
                             " return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2}); })()" % json.dumps(selector)))
        origin = view.get_window().get_origin()[-2:]
        t.XTestFakeMotionEvent(display, -1, int(origin[0] + rect["x"]), int(origin[1] + rect["y"]), 0)
        t.XTestFakeButtonEvent(display, 1, True, 0)
        t.XTestFakeButtonEvent(display, 1, False, 0)
        x.XFlush(display)

    def shot(path):
        root = Gdk.get_default_root_window()
        ox, oy = window.get_window().get_origin()[-2:]
        pixbuf = Gdk.pixbuf_get_from_window(root, ox, oy, window.get_allocated_width(), window.get_allocated_height())
        pixbuf.savev(str(path), "png", [], [])

    (DIR / "ready").write_text(str(os.getpid()))
    last = -1
    while True:
        pump(0.2)
        command_file = DIR / "cmd.json"
        if not command_file.exists():
            continue
        try:
            command = json.loads(command_file.read_text())
        except ValueError:
            continue
        if command.get("id", -1) <= last:
            continue
        last = command["id"]
        result = {"id": last, "op": command["op"]}
        try:
            op = command["op"]
            if op == "open":
                view.load_uri(command["url"])
            elif op == "click":
                click(command["selector"])
            elif op == "type":
                type_text(command["text"])
            elif op == "key":
                key(command["name"])
            elif op == "upload":
                pending_file["path"] = str(Path(command["path"]).resolve())
                click(command["selector"])
            elif op == "quit":
                (DIR / f"out-{last}.json").write_text(json.dumps(result))
                return 0
            pump(float(command.get("wait", 2.5)))
            result.update(json.loads(js(LOOK)))
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            result["error"] = str(error)
        try:
            shot(DIR / f"shot-{last}.png")
        except Exception as error:  # noqa: BLE001 — screenshot problems are reported, not fatal
            result["shot_error"] = str(error)
        (DIR / f"out-{last}.json").write_text(json.dumps(result, ensure_ascii=False))


def main():
    if sys.argv[1:2] == ["--inside"]:
        return inside()
    display = os.environ.get("ZKEY_TEST_DISPLAY")
    if not display:
        print("NOT_MEASURABLE: needs a private display (ZKEY_TEST_DISPLAY)")
        return 2
    env = dict(os.environ, DISPLAY=display, GDK_BACKEND="x11", NO_AT_BRIDGE="1", GIO_USE_VFS="local",
               WEBKIT_DISABLE_COMPOSITING_MODE="1", GTK_IM_MODULE="gtk-im-context-simple",
               # Xvfb has no DRI3 device; use the software path, not GPU DMA-BUF.
               WEBKIT_DISABLE_DMABUF_RENDERER="1", LIBGL_ALWAYS_SOFTWARE="1")
    if sys.argv[1:] not in ([], ["--verify-site"]):
        print("usage: web-driver.py [--verify-site]")
        return 2
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), "--inside", *sys.argv[1:]], env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
