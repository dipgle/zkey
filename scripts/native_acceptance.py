#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real XTest keystrokes into GTK widgets on the user's Xwayland display.

Only synthetic test strings. No DOM insertion or InputContext API substitutes.
Private IBus daemon; never changes the system's fcitx5/IBus input sources.
"""
from pathlib import Path
import ctypes as C
import os
import subprocess
import sys
import time
from x11_activation import activate, free_position, is_active

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402  (never dbus-run-session directly)
# ZKEY_PACKAGE_ROOT: acceptance of an INSTALLED copy (scripts/install-user.py), e.g.
# <prefix>/lib/zkey. Default = this repository.
PACKAGE = Path(os.environ.get("ZKEY_PACKAGE_ROOT", ROOT)).resolve()
sys.path.insert(0, str(PACKAGE))


def inside():
    import zkey.runtime
    if not Path(zkey.runtime.__file__).resolve().is_relative_to(PACKAGE):
        raise RuntimeError(f"Loaded {zkey.runtime.__file__}, not the package under test {PACKAGE}")
    print(f"PACKAGE: {PACKAGE}", flush=True)
    from zkey.runtime import isolated_engine
    with isolated_engine() as (env, _bus, _children):
        os.environ.update(env)
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkX11", "3.0")
        from gi.repository import Gdk, GdkX11, GLib, Gtk
        initialized, _args = Gtk.init_check([])
        if not initialized:
            print("NOT_MEASURABLE: cannot open native X11 display")
            return 2
        window = Gtk.Window(title="zkey — kiểm gõ thật (dữ liệu giả)")
        window.set_default_size(620, 330)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_border_width(24)
        window.add(box)
        entry = Gtk.Entry()
        password = Gtk.Entry()
        password.set_visibility(False)
        password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        # Multi-line field for Enter inside a burst. Out of the Tab chain until
        # its phase; then focused by a real click like the entry.
        lines = Gtk.TextView()
        lines.set_size_request(-1, 70)
        lines.set_can_focus(False)
        for widget in (Gtk.Label(label="zkey: chữ nhận theo từng phím"), entry,
                       Gtk.Label(label="Mật khẩu giả: phím nguyên trạng"), password, lines):
            box.pack_start(widget, False, False, 0)
        visible_preedits = []
        entry.connect("preedit-changed", lambda _entry, text: visible_preedits.append(bool(text)))
        password.connect("preedit-changed", lambda _entry, text: visible_preedits.append(bool(text)))
        lines.connect("preedit-changed", lambda _view, text: visible_preedits.append(bool(text)))
        errors = []
        def log_error(_domain, _level, message, _data):
            errors.append(message)
        handlers = [GLib.log_set_handler(domain, GLib.LogLevelFlags.LEVEL_WARNING | GLib.LogLevelFlags.LEVEL_CRITICAL,
                                        log_error, None) for domain in ("Gtk", "Gdk", "IBUS")]
        presses = []
        entry.connect("button-press-event", lambda *_args: presses.append(1) and False)
        # GTK3 maps new X11 windows without a user time when nothing launched
        # them via startup notification; Mutter then denies focus. Stamp a
        # fresh server time, as a launcher would.
        window.realize()
        placement = C.CDLL("libX11.so.6")
        placement.XOpenDisplay.argtypes, placement.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        placement.XDefaultRootWindow.argtypes, placement.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
        placement.XInternAtom.argtypes, placement.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
        placement.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int,
            C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
            C.POINTER(C.POINTER(C.c_ubyte))]
        placement.XFree.argtypes = [C.c_void_p]
        placement.XCloseDisplay.argtypes = [C.c_void_p]
        probe_display = placement.XOpenDisplay(os.environ["DISPLAY"].encode())
        if not probe_display:
            raise RuntimeError("X11 display unavailable for window placement")
        try:
            spot = free_position(placement, probe_display, 620, 330)
        finally:
            placement.XCloseDisplay(probe_display)
        if spot is not None:
            window.move(*spot)
        print(f"PLACEMENT: {'free spot ' + str(spot) if spot else 'no free spot; default placement'}", flush=True)
        user_time = GdkX11.x11_get_server_time(window.get_window())
        GdkX11.X11Window.set_user_time(window.get_window(), user_time)
        window.show_all()
        window.present_with_time(user_time)
        entry.grab_focus()
        context = GLib.MainContext.default()
        def pump(seconds=0.08):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while context.pending():
                    context.iteration(False)
                time.sleep(0.002)
        pump(0.3)
        xid = GdkX11.X11Window.get_xid(window.get_window())
        x11 = C.CDLL("libX11.so.6")
        xtest = C.CDLL("libXtst.so.6")
        x11.XOpenDisplay.argtypes, x11.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        x11.XStringToKeysym.argtypes, x11.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        x11.XKeysymToKeycode.argtypes, x11.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
        x11.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        x11.XGetInputFocus.argtypes = [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]
        x11.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                                   C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
        x11.XFlush.argtypes = [C.c_void_p]
        x11.XSync.argtypes = [C.c_void_p, C.c_int]
        x11.XCloseDisplay.argtypes = [C.c_void_p]
        xtest.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        xtest.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]
        xtest.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        display = x11.XOpenDisplay(os.environ["DISPLAY"].encode())
        if not display:
            raise RuntimeError("XTest display unavailable")
        try:
            try:
                activate(x11, display, xid, lambda: pump(0.02))
                refused = None
            except RuntimeError as error:
                # Mutter may refuse programmatic activation (focus-stealing
                # prevention). Fall back to what a user does: one real click
                # on our entry; keys stay gated on our window being active.
                refused = error
            if refused is None:
                x11.XSetInputFocus(display, xid, 2, 0)
                x11.XSync(display, False)
            pump(0.2)
            coordinates = entry.translate_coordinates(window, entry.get_allocated_width()//2, entry.get_allocated_height()//2)
            if coordinates is None:
                raise RuntimeError("Cannot locate the test entry")
            local_x, local_y = coordinates[-2:]
            root_x, root_y = window.get_window().get_origin()[-2:]
            xtest.XTestFakeMotionEvent(display, -1, root_x+local_x, root_y+local_y, 0)
            for _click in range(1 if refused else 2):
                xtest.XTestFakeButtonEvent(display, 1, True, 0)
                xtest.XTestFakeButtonEvent(display, 1, False, 0)
                x11.XFlush(display)
                pump(0.05)
            if refused is not None:
                until = time.monotonic() + 2
                while not is_active(x11, display, xid) and time.monotonic() < until:
                    pump(0.02)
                if not is_active(x11, display, xid):
                    raise RuntimeError(f"{refused}; a click on the test entry did not focus it either "
                                       f"(entry button presses received={len(presses)})")
                print("ACTIVATION: compositor refused request; focused by one real click on the test entry", flush=True)
            def send(name, control=False):
                focus, revert = C.c_ulong(), C.c_int()
                x11.XGetInputFocus(display, C.byref(focus), C.byref(revert))
                if not is_active(x11, display, xid):
                    raise RuntimeError("Compositor active window changed; stopped before typing")
                candidate = focus.value
                for _level in range(8):
                    if candidate == xid:
                        break
                    root, parent, children, count = C.c_ulong(), C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
                    result = x11.XQueryTree(display, candidate, C.byref(root), C.byref(parent), C.byref(children), C.byref(count))
                    if children:
                        x11.XFree(children)
                    if not result or not parent.value or parent.value == candidate:
                        break
                    candidate = parent.value
                if candidate != xid:
                    raise RuntimeError("Focus left the test window; stopped before injecting a key")
                code = x11.XKeysymToKeycode(display, x11.XStringToKeysym(name.encode()))
                modifier = x11.XKeysymToKeycode(display, x11.XStringToKeysym(b"Control_L"))
                if not code:
                    raise RuntimeError("Requested test key is unavailable")
                if control:
                    xtest.XTestFakeKeyEvent(display, modifier, True, 0)
                xtest.XTestFakeKeyEvent(display, code, True, 0)
                xtest.XTestFakeKeyEvent(display, code, False, 0)
                if control:
                    xtest.XTestFakeKeyEvent(display, modifier, False, 0)
                x11.XFlush(display)
            def expect(widget, text):
                until = time.monotonic() + 3
                while widget.get_text() != text and time.monotonic() < until:
                    pump(0.01)
                if widget.get_text() != text:
                    raise AssertionError(f"Synthetic text mismatch: expected={text!r}, actual={widget.get_text()!r}")
                if errors:
                    raise RuntimeError("Native toolkit warnings: " + "; ".join(errors))
            expected = ("t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng")
            delays = []
            for key, text in zip("tieengs", expected):
                sent = time.monotonic()
                send(key)
                while entry.get_text() != text and time.monotonic() - sent < 3:
                    while context.pending():
                        context.iteration(False)
                    time.sleep(0.0005)
                delays.append((time.monotonic() - sent) * 1000)
                expect(entry, text)
            # Key-to-widget-text in this process (includes engine reply, not screen paint).
            print(f"KEY-TO-TEXT ms: median={sorted(delays)[len(delays)//2]:.1f} max={max(delays):.1f} "
                  f"(n={len(delays)}, sync={os.environ.get('IBUS_ENABLE_SYNC_MODE', 'unset')})", flush=True)
            send("space")
            expect(entry, "tiếng ")
            for key in "vieetj":
                send(key)
                pump(0.035)
            expect(entry, "tiếng việt")
            send("BackSpace")
            expect(entry, "tiếng việ")
            send("t")
            expect(entry, "tiếng việt")
            send("Home")
            pump()
            send("b")
            expect(entry, "btiếng việt")
            send("Tab")
            pump(0.15)
            for key in "as":
                send(key)
                pump(0.06)
            expect(password, "as")
            send("Tab")
            pump(0.1)
            if not entry.is_focus():
                raise AssertionError("Tab did not return to the normal entry")
            for _round in range(10):
                send("a", control=True)
                pump(0.03)
                send("BackSpace")
                expect(entry, "")
                for key in "tieengs vieetj":
                    send("space" if key == " " else key)
                expect(entry, "tiếng việt")
            # Native keys (Backspace, Enter) inside a 0 ms burst: the app may
            # queue them behind our commits. Reference = the same keys typed
            # slowly; two references are also pinned by hand. Every mismatch
            # is collected before failing, with its round.
            def view_text(view):
                buffer = view.get_buffer()
                return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            def settle(read, seconds=3):
                # Stable for 0.3 s, or the deadline: returns what the app shows.
                last, since, until = read(), time.monotonic(), time.monotonic() + seconds
                while time.monotonic() < until:
                    pump(0.02)
                    now = read()
                    if now != last:
                        last, since = now, time.monotonic()
                    elif time.monotonic() - since >= 0.3:
                        break
                return last
            def clear(read):
                send("a", control=True)
                pump(0.03)
                send("BackSpace")
                if settle(read) != "":
                    raise AssertionError("Cannot clear the field before a burst case")
            def keys(text):
                names = {" ": "space", "\b": "BackSpace", "\n": "Return"}
                return [names.get(ch, ch) for ch in text]
            entry_cases = (("vieetj\bt", "việt"), ("tieengs\bf", None),
                           ("xin chaof\b\baf", None), ("dduowcj\b\bc", None))
            line_cases = (("tieengs\nvieetj", "tiếng\nviệt"), ("xin\nchaof\nbanj", None))
            lines.set_can_focus(True)
            mismatches, rounds = [], 5
            for widget, read, cases in ((entry, entry.get_text, entry_cases),
                                        (lines, lambda: view_text(lines), line_cases)):
                if widget is lines:
                    origin = lines.translate_coordinates(window, 20, 20)
                    xtest.XTestFakeMotionEvent(display, -1, root_x+origin[0], root_y+origin[1], 0)
                    xtest.XTestFakeButtonEvent(display, 1, True, 0)
                    xtest.XTestFakeButtonEvent(display, 1, False, 0)
                    x11.XFlush(display)
                    until = time.monotonic() + 2
                    while not lines.is_focus() and time.monotonic() < until:
                        pump(0.02)
                    if not lines.is_focus():
                        raise RuntimeError("A real click did not focus the multi-line field")
                for typed, pinned in cases:
                    clear(read)
                    for name in keys(typed):
                        send(name)
                        pump(0.12)
                    reference = settle(read)
                    if pinned is not None and reference != pinned:
                        mismatches.append(f"slow {typed!r}: expected={pinned!r} actual={reference!r}")
                    for round_ in range(rounds):
                        clear(read)
                        for name in keys(typed):
                            send(name)
                        actual = settle(read)
                        if actual != reference:
                            mismatches.append(f"burst {typed!r} round {round_+1}/{rounds}: slow={reference!r} burst={actual!r}")
            total = rounds * (len(entry_cases) + len(line_cases))
            print(f"BURST+NATIVE: {total - sum(m.startswith('burst') for m in mismatches)}/{total} burst rounds equal to slow typing; "
                  f"{sum(m.startswith('slow') for m in mismatches)} slow reference mismatches", flush=True)
            if mismatches:
                raise AssertionError("Burst with native keys differs: " + " | ".join(mismatches))
            if errors:
                raise RuntimeError("Native toolkit warnings: " + "; ".join(errors))
            if any(visible_preedits):
                raise AssertionError("Visible preedit in direct/password mode")
            engine_log = PACKAGE / ".tmp" / (Path(env["IBUS_ADDRESS"].split("unix:path=", 1)[1]).parent.name + ".log")
            observed = engine_log.read_text().count("key-state ")
            if observed < len("tieengs"):
                raise AssertionError(f"Wrong input engine: private zkey observed only {observed} key calls")
            pump(0.35)
            pixbuf = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                              window.get_allocated_width(), window.get_allocated_height())
            if pixbuf is None:
                raise RuntimeError("Cannot capture native verification window")
            pixbuf.savev(str(ROOT / ".tmp/native-gtk.png"), "png", [], [])
            # XGetImage excludes GTK input child windows on this Xwayland host.
            # Export the same already-typed widgets; never seed replacement text.
            export = Gtk.OffscreenWindow()
            export.set_default_size(620, 330)
            window.remove(box)
            export.add(box)
            export.show_all()
            pump(0.2)
            rendered = export.get_pixbuf()
            if rendered is None:
                raise RuntimeError("Typed widget render unavailable")
            rendered.savev(str(ROOT / ".tmp/native-gtk-render.png"), "png", [], [])
            export.destroy()
            print("PASS native GTK3/XTest: 7 per-key prefixes; 10 burst phrases; burst with native Backspace/Enter equal to slow typing; word boundary; Vietnamese; native Backspace; caret move; focus/password bypass; no visible preedit; 0 toolkit warnings.")
            print("UI screenshot: .tmp/native-gtk.png; does not cover Chrome/Electron/Wayland-native/VTE yet.")
            return 0
        finally:
            x11.XCloseDisplay(display)
            window.destroy()
            for domain, handler in zip(("Gtk", "Gdk", "IBUS"), handlers):
                GLib.log_remove_handler(domain, handler)


def main():
    if sys.argv[1:] == ["--inside"]:
        try:
            return inside()
        except (OSError, RuntimeError, AssertionError) as error:
            print(f"NATIVE FAILED: {error}", file=sys.stderr)
            return 1
    env = os.environ.copy()
    if test_display := os.environ.get("ZKEY_TEST_DISPLAY"):
        # Private Xvfb from accept-xvfb.sh: never touch the user's desktop.
        env["DISPLAY"] = test_display
        env.pop("WAYLAND_DISPLAY", None)
    else:
        result = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True)
        if result.returncode:
            print("NOT_MEASURABLE: cannot read desktop environment")
            return 2
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR"}:
                env[key] = value
    if not env.get("DISPLAY"):
        print("NOT_MEASURABLE: desktop has no Xwayland DISPLAY")
        return 2
    env.pop("IBUS_USE_PORTAL", None)
    env.update(ZKEY_ISOLATED_BUS="1", GTK_IM_MODULE="ibus", GDK_BACKEND="x11", NO_AT_BRIDGE="1", GIO_USE_VFS="local", ZKEY_TRACE="1")
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), "--inside"], env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
