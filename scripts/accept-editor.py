#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Type into our standalone GNOME Text Editor via XTest, read its visible UI.

Only inject into windows carrying the PID of the app we just opened. Read the
accessible document after each key; never seed text or call app internals.
"""
from pathlib import Path
import ctypes as C
import json
import os
import subprocess
import time
from editor_ui import document
from x11_activation import activate, is_active

ROOT = Path(__file__).resolve().parents[1]
MARKER = Path(os.environ.get("ZKEY_APP_PID_FILE", ROOT / ".tmp/editor-app.json")).resolve()
if not MARKER.is_relative_to(ROOT / ".tmp"):
    raise ValueError("Application marker must be within zkey/.tmp")
application = json.loads(MARKER.read_text())
if not os.environ.get("ZKEY_TEST_DISPLAY"):
    # Desktop Xwayland needs Mutter's cookie; a private Xvfb (accept-xvfb.sh) does not.
    desktop = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True, check=True)
    for line in desktop.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key == "XAUTHORITY":
            os.environ[key] = value
x = C.CDLL("libX11.so.6")
t = C.CDLL("libXtst.so.6")
x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
x.XInternAtom.argtypes, x.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
                                 C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                 C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ubyte))]
x.XFree.argtypes = [C.c_void_p]
x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
x.XRaiseWindow.argtypes = [C.c_void_p, C.c_ulong]
x.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                         C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
x.XTranslateCoordinates.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_int, C.c_int,
                                    C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_ulong)]
x.XGetGeometry.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int),
                           C.POINTER(C.c_int), C.POINTER(C.c_uint), C.POINTER(C.c_uint),
                           C.POINTER(C.c_uint), C.POINTER(C.c_uint)]
x.XGetInputFocus.argtypes = [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]
x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
x.XFlush.argtypes = [C.c_void_p]
x.XSync.argtypes = [C.c_void_p, C.c_int]
x.XCloseDisplay.argtypes = [C.c_void_p]
t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
t.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]
t.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
display = x.XOpenDisplay(application["display"].encode())
if not display:
    raise RuntimeError("Cannot open the application's X11 display")


def property_values(window, name):
    atom = x.XInternAtom(display, name.encode(), False)
    actual, fmt, count, remaining = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
    data = C.POINTER(C.c_ubyte)()
    result = x.XGetWindowProperty(display, window, atom, 0, 4096, False, 0,
                                  C.byref(actual), C.byref(fmt), C.byref(count), C.byref(remaining), C.byref(data))
    try:
        if result or fmt.value != 32 or not data:
            return []
        return list(C.cast(data, C.POINTER(C.c_ulong))[:count.value])
    finally:
        if data:
            x.XFree(data)


def owned(window):
    # GTK4 can put keyboard focus on an input child without _NET_WM_PID.
    for _level in range(8):
        pids = property_values(window, "_NET_WM_PID")
        if pids:
            return pids == [application["pid"]]
        root, parent, children, count = C.c_ulong(), C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
        result = x.XQueryTree(display, window, C.byref(root), C.byref(parent), C.byref(children), C.byref(count))
        if children:
            x.XFree(children)
        if not result or not parent.value or parent.value == window:
            break
        window = parent.value
    return False


class Attributes(C.Structure):
    _fields_ = [("x", C.c_int), ("y", C.c_int), ("width", C.c_int), ("height", C.c_int),
                ("border_width", C.c_int), ("depth", C.c_int), ("visual", C.c_void_p), ("root", C.c_ulong),
                ("class_", C.c_int), ("bit_gravity", C.c_int), ("win_gravity", C.c_int),
                ("backing_store", C.c_int), ("backing_planes", C.c_ulong), ("backing_pixel", C.c_ulong),
                ("save_under", C.c_int), ("colormap", C.c_ulong), ("map_installed", C.c_int),
                ("map_state", C.c_int), ("padding", C.c_long * 16)]


x.XGetWindowAttributes.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(Attributes)]


def viewable(window):
    attributes = Attributes()
    return bool(x.XGetWindowAttributes(display, window, C.byref(attributes))) and attributes.map_state == 2


def top_level_windows(root):
    # No window manager on a private Xvfb: application toplevels are root children.
    parent, children, count = C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
    if not x.XQueryTree(display, root, C.byref(C.c_ulong()), C.byref(parent), C.byref(children), C.byref(count)):
        return []
    try:
        return [children[index] for index in range(count.value)]
    finally:
        if children:
            x.XFree(children)


try:
    root = x.XDefaultRootWindow(display)
    deadline = time.monotonic() + 8
    windows = []
    while not windows and time.monotonic() < deadline:
        candidates = property_values(root, "_NET_CLIENT_LIST") or top_level_windows(root)
        windows = [window for window in candidates if owned(window) and viewable(window)]
        time.sleep(0.04)
    if not windows:
        raise RuntimeError("No mapped Text Editor window for the launched PID")
    window = windows[0]
    activate(x, display, window)
    x.XRaiseWindow(display, window)
    x.XSetInputFocus(display, window, 2, 0)
    x.XSync(display, False)
    time.sleep(0.3)
    def send(key, modifier=None, pause=0.055):
        focus, revert = C.c_ulong(), C.c_int()
        x.XGetInputFocus(display, C.byref(focus), C.byref(revert))
        if not is_active(x, display, window):
            raise RuntimeError("Compositor active window changed; stopped before typing")
        if not owned(focus.value):
            raise RuntimeError(f"Focus left our Text Editor process (focus={focus.value}, target={window}); stopped before typing")
        symbol = ord(key) if len(key) == 1 else x.XStringToKeysym(key.encode())
        code = x.XKeysymToKeycode(display, symbol)
        mod = x.XKeysymToKeycode(display, x.XStringToKeysym(modifier.encode())) if modifier else None
        if not code:
            raise RuntimeError("Test key unavailable")
        if mod:
            t.XTestFakeKeyEvent(display, mod, True, 0)
        t.XTestFakeKeyEvent(display, code, True, 0)
        t.XTestFakeKeyEvent(display, code, False, 0)
        if mod:
            t.XTestFakeKeyEvent(display, mod, False, 0)
        x.XFlush(display)
        if pause:
            time.sleep(pause)
    # This is our fresh standalone test document. Dismiss a previous failed
    # Save dialog before retrying, then replace only this synthetic fixture.
    send("Escape")
    time.sleep(0.15)
    Atspi, editor = document(application["pid"])
    bounds = Atspi.Component.get_extents(editor.get_component_iface(), Atspi.CoordType.SCREEN)
    if bounds.width <= 0 or bounds.height <= 0:
        raise RuntimeError("Document UI has no visible bounds")
    gx, gy, width, height, border, depth = C.c_int(), C.c_int(), C.c_uint(), C.c_uint(), C.c_uint(), C.c_uint()
    geometry_root, translated_child, origin_x, origin_y = C.c_ulong(), C.c_ulong(), C.c_int(), C.c_int()
    if not x.XGetGeometry(display, window, C.byref(geometry_root), C.byref(gx), C.byref(gy),
                          C.byref(width), C.byref(height), C.byref(border), C.byref(depth)):
        raise RuntimeError("Cannot locate the owned editor window")
    x.XTranslateCoordinates(display, window, root, 0, 0, C.byref(origin_x), C.byref(origin_y), C.byref(translated_child))
    # GTK4 reports (0,0) for screen extents on this host. Use the actual X11
    # window origin and its document-area center, then verify UI focus.
    t.XTestFakeMotionEvent(display, -1, origin_x.value + width.value//2, origin_y.value + height.value//2, 0)
    for _click in range(2):
        t.XTestFakeButtonEvent(display, 1, True, 0)
        t.XTestFakeButtonEvent(display, 1, False, 0)
        x.XFlush(display)
        time.sleep(0.08)
    x.XFlush(display)
    time.sleep(0.15)
    editor.clear_cache()
    print(f"DOCUMENT_UI bounds=({bounds.x},{bounds.y},{bounds.width},{bounds.height}) focused={editor.get_state_set().contains(Atspi.StateType.FOCUSED)}", flush=True)
    def expect(text):
        deadline = time.monotonic() + 3
        actual = Atspi.Text.get_text(editor.get_text_iface(), 0, -1).rstrip("\n")
        while actual != text and time.monotonic() < deadline:
            time.sleep(0.01)
            actual = Atspi.Text.get_text(editor.get_text_iface(), 0, -1).rstrip("\n")
        if actual != text:
            raise AssertionError(f"Editor UI differs after real key: expected={text!r}, actual={actual!r}")
    send("a", "Control_L")
    send("BackSpace")
    expect("")
    for key, expected in zip("tieengs", ("t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng")):
        send(key)
        expect(expected)
    for key in " vieetj":
        send(key)
    expect("tiếng việt")
    # Native keys (Backspace, Enter) inside a 0 ms burst, read from the real
    # document. Reference = same keys typed slowly; two references pinned by
    # hand. Every mismatch is collected, with its round (same cases as GTK3).
    def shown():
        return Atspi.Text.get_text(editor.get_text_iface(), 0, -1).rstrip("\n")
    def settle(seconds=3):
        last, since, until = shown(), time.monotonic(), time.monotonic() + seconds
        while time.monotonic() < until:
            time.sleep(0.02)
            now = shown()
            if now != last:
                last, since = now, time.monotonic()
            elif time.monotonic() - since >= 0.3:
                break
        return last
    def clear():
        send("a", "Control_L")
        send("BackSpace")
        left = settle()
        if left != "":
            # Diagnose lost vs reordered keys: slow native keys, document after each.
            trail = []
            for probe in ("BackSpace", "BackSpace", "End", "BackSpace"):
                send(probe, pause=0.2)
                trail.append(f"{probe}->{settle()!r}")
            raise AssertionError(f"Ctrl+A, Backspace left {left!r} in the synthetic document; "
                                 f"then slow keys: {', '.join(trail)}; "
                                 f"mismatches so far: {' | '.join(mismatches) or 'none'}")
    names = {" ": "space", "\b": "BackSpace", "\n": "Return"}
    cases = (("vieetj\bt", "việt"), ("tieengs\bf", None), ("xin chaof\b\baf", None),
             ("dduowcj\b\bc", None), ("tieengs\nvieetj", "tiếng\nviệt"), ("xin\nchaof\nbanj", None))
    mismatches, rounds = [], 5
    for typed, pinned in cases:
        clear()
        for ch in typed:
            send(names.get(ch, ch), pause=0.12)
        reference = settle()
        if pinned is not None and reference != pinned:
            mismatches.append(f"slow {typed!r}: expected={pinned!r} actual={reference!r}")
        for round_ in range(rounds):
            clear()
            for ch in typed:
                send(names.get(ch, ch), pause=0)
            actual = settle()
            if actual != reference:
                mismatches.append(f"burst {typed!r} round {round_+1}/{rounds}: slow={reference!r} burst={actual!r}")
    total = rounds * len(cases)
    print(f"EDITOR BURST+NATIVE: {total - sum(m.startswith('burst') for m in mismatches)}/{total} burst rounds equal to slow typing; "
          f"{sum(m.startswith('slow') for m in mismatches)} slow reference mismatches "
          f"(sync={os.environ.get('ZKEY_CLIENT_SYNC_MODE', 'default')})", flush=True)
    if mismatches:
        raise AssertionError("Editor burst with native keys differs: " + " | ".join(mismatches))
    print("PASS GNOME Text Editor: 7 per-key prefixes and Vietnamese phrase; burst with native Backspace/Enter equal to slow typing; read through the actual document's accessibility UI; app remains open.")
    (ROOT / ".tmp/editor-accepted.json").write_text(json.dumps({"pid": application["pid"], "window": window, "per_key_prefixes": 7, "burst_native_rounds": total}) + "\n")
finally:
    x.XCloseDisplay(display)
    # Independent burst coverage still runs if the GNOME focus check fails.
    # It uses a separate synthetic GTK window and private bus.
    burst = subprocess.call(["bash", str(ROOT / "scripts/desktop-host.sh")])
    if burst:
        print("Native burst regression failed; read .tmp/native-acceptance.log", flush=True)
if burst:
    raise SystemExit(burst)
