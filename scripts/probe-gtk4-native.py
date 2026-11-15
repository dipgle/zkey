#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Probe: does GTK4's IBus module (X11 backend) drop keys an engine refuses?

Control for 15/11: GNOME Text Editor under zkey lost Backspace/End/Ctrl+A in
async mode. Same GTK4 Entry, same XTest keys, two engines:
  zkey         commits letters itself, refuses Backspace
  xkb:us::eng  stock IBus engine, refuses EVERY key (pass-through)
If GTK4 async drops refused keys, xkb loses even letters => not a zkey bug.

Run inside a private display (ZKEY_TEST_DISPLAY), private D-Bus + IBus:
  ZKEY_PROBE_ENGINE=zkey|xkb:us::eng ZKEY_CLIENT_SYNC_MODE=0|1 python3 probe-gtk4-native.py
Synthetic text only. Exit 0 = measured (verdict printed), 2 = not measurable.
"""
from pathlib import Path
import ctypes as C
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def inside():
    from zkey.runtime import isolated_engine
    engine = os.environ.get("ZKEY_PROBE_ENGINE", "zkey")
    with isolated_engine() as (env, bus, _children):
        os.environ.update(env)
        if engine != "zkey" and not bus.set_global_engine(engine):
            print(f"NOT_MEASURABLE: private IBus cannot select {engine}")
            return 2
        active = bus.get_global_engine()
        active = active.get_name() if active else None
        if active != engine:
            print(f"NOT_MEASURABLE: active engine {active!r}, wanted {engine!r}")
            return 2
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11, GLib, Gtk
        if not Gtk.init_check():
            print("NOT_MEASURABLE: cannot open X11 display")
            return 2
        window = Gtk.Window(title="zkey probe GTK4 (dữ liệu giả)")
        window.set_default_size(400, 80)
        entry = Gtk.Entry()
        window.set_child(entry)
        window.present()
        context = GLib.MainContext.default()

        def pump(seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while context.pending():
                    context.iteration(False)
                time.sleep(0.002)
        pump(0.5)
        xid = GdkX11.X11Surface.get_xid(window.get_surface())
        x = C.CDLL("libX11.so.6")
        t = C.CDLL("libXtst.so.6")
        x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
        x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        x.XFlush.argtypes = [C.c_void_p]
        x.XSync.argtypes = [C.c_void_p, C.c_int]
        x.XCloseDisplay.argtypes = [C.c_void_p]
        t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        display = x.XOpenDisplay(os.environ["DISPLAY"].encode())
        if not display:
            print("NOT_MEASURABLE: XTest display unavailable")
            return 2
        try:
            # No window manager on the private Xvfb: focus our toplevel directly.
            x.XSetInputFocus(display, xid, 2, 0)
            x.XSync(display, False)
            entry.grab_focus()
            pump(0.4)
            # GtkEntry delegates focus to an inner GtkText child.
            focus = window.get_focus()
            inside_entry = focus is not None and (focus == entry or focus.is_ancestor(entry))
            if not (inside_entry and window.is_active()):
                print(f"NOT_MEASURABLE: no keyboard focus (focus_in_entry={inside_entry}, active={window.is_active()})")
                return 2

            def send(name):
                code = x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode()))
                if not code:
                    raise RuntimeError(f"Test key {name} unavailable")
                t.XTestFakeKeyEvent(display, code, True, 0)
                t.XTestFakeKeyEvent(display, code, False, 0)
                x.XFlush(display)
                pump(0.25)  # slow on purpose: loss, not ordering
                return entry.get_text()
            trail = [(name, send(name)) for name in ("a", "b", "c", "BackSpace", "Home", "x", "End", "BackSpace")]
        finally:
            x.XCloseDisplay(display)
            window.destroy()
        expected = ["a", "ab", "abc", "ab", "ab", "xab", "xab", "xa"]
        lost = [name for (name, got), want in zip(trail, expected) if got != want]
        sync = os.environ.get("IBUS_ENABLE_SYNC_MODE", "unset")
        print(f"PROBE engine={engine} sync={sync}: " + " ".join(f"{n}->{g!r}" for n, g in trail))
        print(f"VERDICT engine={engine} sync={sync}: {'OK all 8 keys' if not lost else 'WRONG after ' + ','.join(lost)}")
        return 0


def main():
    if sys.argv[1:] == ["--inside"]:
        try:
            return inside()
        except (OSError, RuntimeError) as error:
            print(f"NOT_MEASURABLE: {error}")
            return 2
    display = os.environ.get("ZKEY_TEST_DISPLAY")
    if not display:
        print("NOT_MEASURABLE: run on a private display (ZKEY_TEST_DISPLAY); never the desktop")
        return 2
    env = os.environ.copy()
    env["DISPLAY"] = display
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("IBUS_USE_PORTAL", None)
    env.update(ZKEY_ISOLATED_BUS="1", GTK_IM_MODULE="ibus", GDK_BACKEND="x11", NO_AT_BRIDGE="1",
               GIO_USE_VFS="local", ZKEY_TRACE="1")
    return subprocess.call(["dbus-run-session", "--", sys.executable, str(Path(__file__).resolve()), "--inside"], env=env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
