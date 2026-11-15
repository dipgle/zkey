#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings screen acceptance, end to end across two roles, real XTest keys.

Private Xvfb (ZKEY_TEST_DISPLAY) + private D-Bus + private IBus; config file
under zkey/.tmp (ZKEY_CONFIG_PATH), never the user's.
  1. typing app (GTK3 entry, zkey engine): "hoaf" -> "hoà" with defaults
  2. broken config file: settings screen still opens, shows the error
  3. keyboard only: untick "Đặt dấu hiện đại", Save -> status, file, changes.log
  4. reopen: the choice is shown
  5. typing app again (focus-in reloads config): "hoaf" -> "hòa"
Screens read through the accessibility tree (what is shown), screenshots of
every state in .tmp/settings-*.png. Exit 0 pass, 1 fail, 2 not measurable.
"""
from pathlib import Path
import ctypes as C
import os
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402  (never dbus-run-session directly)
TITLE = "zkey — Thiết lập Telex"


def inside():
    from zkey.runtime import isolated_engine
    config = Path(os.environ["ZKEY_CONFIG_PATH"])
    with isolated_engine() as (env, _bus, _children):
        os.environ.update(env)
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkX11", "3.0")
        from gi.repository import Gdk, GdkX11, GLib, Gtk
        if not Gtk.init_check([])[0]:
            print("NOT_MEASURABLE: cannot open X display")
            return 2
        import editor_ui
        context = GLib.MainContext.default()

        def pump(seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while context.pending():
                    context.iteration(False)
                time.sleep(0.003)

        x = C.CDLL("libX11.so.6")
        t = C.CDLL("libXtst.so.6")
        x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
        x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        x.XRaiseWindow.argtypes = [C.c_void_p, C.c_ulong]
        x.XFlush.argtypes = [C.c_void_p]
        x.XSync.argtypes = [C.c_void_p, C.c_int]
        x.XCloseDisplay.argtypes = [C.c_void_p]
        t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        display = x.XOpenDisplay(os.environ["DISPLAY"].encode())

        def key(name, control=False):
            code = x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode()))
            ctrl = x.XKeysymToKeycode(display, x.XStringToKeysym(b"Control_L"))
            if control:
                t.XTestFakeKeyEvent(display, ctrl, True, 0)
            t.XTestFakeKeyEvent(display, code, True, 0)
            t.XTestFakeKeyEvent(display, code, False, 0)
            if control:
                t.XTestFakeKeyEvent(display, ctrl, False, 0)
            x.XFlush(display)
            pump(0.12)

        def focus_window(xid):
            x.XRaiseWindow(display, xid)
            x.XSetInputFocus(display, xid, 2, 0)
            x.XSync(display, False)
            pump(0.3)

        def shot(name, origin=None, size=None):
            root = Gdk.get_default_root_window()
            ox, oy = origin or (0, 0)
            w, h = size or (root.get_width(), root.get_height())
            pixbuf = Gdk.pixbuf_get_from_window(root, ox, oy, w, h)
            if pixbuf is None:
                raise RuntimeError("Screenshot unavailable")
            path = ROOT / f".tmp/settings-{name}.png"
            pixbuf.savev(str(path), "png", [], [])
            return path

        # --- the typing application (role B) ---
        window = Gtk.Window(title="zkey — ô gõ thử (dữ liệu giả)")
        window.set_default_size(420, 80)
        entry = Gtk.Entry()
        window.add(entry)
        window.move(700, 40)
        window.show_all()
        pump(0.4)
        app_xid = GdkX11.X11Window.get_xid(window.get_window())

        def type_word():
            focus_window(app_xid)
            entry.grab_focus()
            pump(0.2)
            key("a", control=True)
            key("BackSpace")
            for ch in "hoaf":
                key(ch)
            until = time.monotonic() + 3
            while time.monotonic() < until and len(entry.get_text()) < 3:
                pump(0.02)
            pump(0.3)
            return entry.get_text()

        results = {"before": type_word()}

        # --- the settings screen (role A) ---
        settings_env = dict(env, GTK_IM_MODULE="gtk-im-context-simple", ZKEY_CONFIG_PATH=str(config))
        settings_env.pop("NO_AT_BRIDGE", None)
        processes = []

        def open_settings():
            process = subprocess.Popen([sys.executable, "-m", "zkey.settings"], cwd=ROOT, env=settings_env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(process)
            Atspi, app = editor_ui.connect(process.pid)
            deadline = time.monotonic() + 8
            frame = None
            while time.monotonic() < deadline and frame is None:
                for node in editor_ui.walk(app):
                    if node.get_role() == Atspi.Role.FRAME and node.get_name() == TITLE:
                        frame = node
                pump(0.05)
            if frame is None:
                raise RuntimeError("Settings window not shown")
            extents = frame.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            return process, Atspi, app, frame, extents

        def widgets(Atspi, app):
            found = {}
            for node in editor_ui.walk(app):
                role, name = node.get_role(), node.get_name() or ""
                if role == Atspi.Role.CHECK_BOX and "hiện đại" in name:
                    found["modern"] = node
                elif role == Atspi.Role.CHECK_BOX and "Bật" in name:
                    found["enabled"] = node
                elif role == Atspi.Role.PUSH_BUTTON and "Lưu" in name:
                    found["save"] = node
                elif role == Atspi.Role.LABEL and ("Thiết lập áp dụng" in name or "lỗi" in name or "Đã lưu" in name
                                                   or "Không lưu" in name):
                    found["status"] = node
            return found

        def checked(Atspi, node):
            node.clear_cache()  # AT-SPI caches states; read what is shown now
            return node.get_state_set().contains(Atspi.StateType.CHECKED)

        def focused(Atspi, node):
            node.clear_cache()
            return node.get_state_set().contains(Atspi.StateType.FOCUSED)

        def focus_trail(Atspi, app):
            app.clear_cache()
            return [f"{n.get_role_name()}:{(n.get_name() or '')[:20]}" for n in editor_ui.walk(app)
                    if (n.clear_cache() or True) and n.get_state_set().contains(Atspi.StateType.FOCUSED)]

        x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
        x.XInternAtom.argtypes, x.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
        x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
                                         C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                         C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ubyte))]
        x.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                                 C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
        x.XFree.argtypes = [C.c_void_p]

        def settings_xid(pid):
            """The settings toplevel: a root child (no WM on this Xvfb) carrying its PID."""
            atom = x.XInternAtom(display, b"_NET_WM_PID", False)
            root = x.XDefaultRootWindow(display)
            parent, children, count = C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
            if not x.XQueryTree(display, root, C.byref(C.c_ulong()), C.byref(parent), C.byref(children), C.byref(count)):
                return None
            kids = [children[i] for i in range(count.value)]
            if children:
                x.XFree(children)
            for kid in kids:
                actual, fmt, n, rest = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
                data = C.POINTER(C.c_ubyte)()
                if x.XGetWindowProperty(display, kid, atom, 0, 1, False, 0, C.byref(actual), C.byref(fmt),
                                        C.byref(n), C.byref(rest), C.byref(data)) == 0 and data:
                    value = C.cast(data, C.POINTER(C.c_ulong))[0] if fmt.value == 32 and n.value else None
                    x.XFree(data)
                    if value == pid and window_title(kid) == TITLE:
                        return kid  # the mapped toplevel, not GDK's hidden leader window (same PID)
            return None

        def window_title(window):
            atom = x.XInternAtom(display, b"_NET_WM_NAME", False)
            utf8 = x.XInternAtom(display, b"UTF8_STRING", False)
            actual, fmt, n, rest = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
            data = C.POINTER(C.c_ubyte)()
            if x.XGetWindowProperty(display, window, atom, 0, 1024, False, utf8, C.byref(actual), C.byref(fmt),
                                    C.byref(n), C.byref(rest), C.byref(data)) or not data:
                return ""
            try:
                return bytes(data[:n.value]).decode("utf-8", "replace")
            finally:
                x.XFree(data)

        try:
            # 2. broken file: the screen still opens and says what is wrong
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text("enabled = maybe\n")
            process, Atspi, app, frame, box = open_settings()
            pump(0.5)
            w = widgets(Atspi, app)
            status = w["status"].get_name()
            if "lỗi" not in status or not checked(Atspi, w["modern"]):
                raise AssertionError(f"Broken config not reported with defaults shown: status={status!r}")
            shot("error", (box.x, box.y), (box.width, box.height))
            results["error_status"] = status

            # 3. keyboard only: focus the screen, Tab to the checkbox, untick, Tab to Save, press
            xid = settings_xid(process.pid)
            if xid is None:
                raise RuntimeError("Settings X window (by _NET_WM_PID) not found")
            focus_window(xid)  # what a click or a window manager does; no accessibility action
            for _ in range(6):
                if focused(Atspi, w["modern"]):
                    break
                key("Tab")
            if not focused(Atspi, w["modern"]):
                raise AssertionError(f"Tab never reached the tone checkbox; focused now: {focus_trail(Atspi, app)}; "
                                     f"frame active={frame.get_state_set().contains(Atspi.StateType.ACTIVE)}")
            key("space")
            if checked(Atspi, w["modern"]):
                raise AssertionError("Space did not untick the tone checkbox")
            for _ in range(6):
                if focused(Atspi, w["save"]):
                    break
                key("Tab")
            if not focused(Atspi, w["save"]):
                raise AssertionError("Tab never reached the Save button")
            key("space")
            pump(0.4)
            app.clear_cache()
            status = widgets(Atspi, app)["status"].get_name()
            if "Đã lưu" not in status:
                raise AssertionError(f"Save not confirmed on screen: {status!r}")
            shot("saved", (box.x, box.y), (box.width, box.height))
            results["saved_status"] = status
            text = config.read_text()
            if "modern_tone = false" not in text:
                raise AssertionError(f"Saved file does not hold the choice: {text!r}")
            log = (config.parent / "changes.log").read_text().splitlines()
            if not log or "modern_tone=true->false" not in log[-1]:
                raise AssertionError(f"changes.log missing the change: {log!r}")
            results["log"] = log[-1]
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)

            # 4. reopen: the stored choice is shown
            process, Atspi, app, frame, box = open_settings()
            pump(0.5)
            w = widgets(Atspi, app)
            if checked(Atspi, w["modern"]) or not checked(Atspi, w["enabled"]):
                raise AssertionError("Reopened screen does not show the saved choice")
            shot("reopened", (box.x, box.y), (box.width, box.height))
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        finally:
            for process in processes:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)

        # 5. the typing application picks the new setting up on focus-in
        results["after"] = type_word()
        x.XCloseDisplay(display)
        window.destroy()
        print(f"TYPING before={results['before']!r} after={results['after']!r}")
        print(f"SCREEN error={results['error_status']!r}")
        print(f"SCREEN saved={results['saved_status']!r}")
        print(f"CHANGES.LOG {results['log']}")
        if results["before"] != "hoà" or results["after"] != "hòa":
            raise AssertionError("Typing did not follow the setting changed on the settings screen "
                                 f"(expected 'hoà' then 'hòa')")
        print("PASS settings: broken file reported with defaults; keyboard untick + Save; file + changes.log; "
              "reopened shows choice; typing app follows it (hoà -> hòa). Screenshots .tmp/settings-{error,saved,reopened}.png")
        return 0


def main():
    if sys.argv[1:] == ["--inside"]:
        try:
            return inside()
        except AssertionError as error:
            print(f"SETTINGS FAILED: {error}")
            return 1
        except (OSError, RuntimeError, KeyError) as error:
            print(f"NOT_MEASURABLE: {error!r}")
            return 2
    display = os.environ.get("ZKEY_TEST_DISPLAY")
    if not display:
        print("NOT_MEASURABLE: run on a private display (ZKEY_TEST_DISPLAY); never the desktop")
        return 2
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="settings-accept-", dir=ROOT / ".tmp") as scratch:
        env = os.environ.copy()
        env["DISPLAY"] = display
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("IBUS_USE_PORTAL", None)
        env.update(ZKEY_ISOLATED_BUS="1", GTK_IM_MODULE="ibus", GDK_BACKEND="x11", NO_AT_BRIDGE="1",
                   GIO_USE_VFS="local", ZKEY_TRACE="1",
                   ZKEY_CONFIG_PATH=str(Path(scratch) / "zkey/config.toml"))
        return private_bus.call([sys.executable, str(Path(__file__).resolve()), "--inside"], env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
