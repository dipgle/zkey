#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real keys into the real ptyxis app running the user's bash (~/.bashrc).

Run inside a private Xvfb (ZKEY_TEST_DISPLAY). ptyxis starts standalone under
zkey's private IBus/D-Bus (zkey.launch). Verdict comes from what bash actually
received, written by bash itself to .tmp/ptyxis-out.txt: line 1 the Vietnamese
phrase typed inside quotes, line 2 SAME if a one-time secret typed with ECHO
off reached the shell unchanged. Synthetic strings only; nothing typed is logged.
"""
from pathlib import Path
import ctypes as C
import json
import os
import signal
import subprocess
import sys
import time
from x11_activation import activate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402  (never dbus-run-session directly)
OUT = ROOT / ".tmp/ptyxis-out.txt"
MARKER = ROOT / ".tmp/ptyxis-app.json"
SESSION_LOG = ROOT / ".tmp/ptyxis-session.log"
SHIFTED = set('"<>_:|&$!?{}()+~@#%^*') | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
NAMES = {" ": "space", "-": "minus", "$": "dollar", "=": "equal", '"': "quotedbl", "[": "bracketleft",
         "]": "bracketright", "'": "apostrophe", "\\": "backslash", "&": "ampersand", "|": "bar",
         ";": "semicolon", "/": "slash", ".": "period", ">": "greater", "_": "underscore", "\n": "Return"}


def main():
    display_name = os.environ.get("ZKEY_TEST_DISPLAY")
    if not display_name:
        print("NOT_MEASURABLE: run inside a private Xvfb (ZKEY_TEST_DISPLAY unset)")
        return 2
    for path in (OUT, MARKER):
        if path.exists():
            path.write_text("")
    env = os.environ.copy()
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("IBUS_USE_PORTAL", None)
    # The real product path: ptyxis as the user runs it, the shell plugin doing
    # Telex. Not via `zkey --run` (its isolated session destabilises ptyxis on
    # Xvfb: measured 15/11, see docs/verification.md). Terminals bypass the IME.
    env.update(DISPLAY=display_name, GDK_BACKEND="x11", GTK_IM_MODULE="gtk-im-context-simple")
    launcher = private_bus.popen(["ptyxis", "--standalone"], env, child_real_runtime=True, cwd=ROOT,
                                stdout=SESSION_LOG.open("w"), stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        found = subprocess.run(["pgrep", "-P", str(launcher.pid), "-x", "ptyxis"], capture_output=True, text=True)
        if found.stdout.strip():
            MARKER.write_text(json.dumps({"pid": int(found.stdout.split()[0])}) + "\n")
            break
        time.sleep(0.1)
    try:
        return run(display_name)
    finally:
        os.killpg(launcher.pid, signal.SIGTERM)
        try:
            launcher.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(launcher.pid, signal.SIGKILL)


def run(display_name):
    deadline = time.monotonic() + 20
    def marker():
        return MARKER.read_text().strip() if MARKER.exists() else ""
    while time.monotonic() < deadline and not marker():
        time.sleep(0.1)
    if not marker():
        raise RuntimeError("ptyxis did not start under the zkey launcher")
    pid = json.loads(MARKER.read_text())["pid"]
    x = C.CDLL("libX11.so.6")
    t = C.CDLL("libXtst.so.6")
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
    x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
    x.XInternAtom.argtypes, x.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
    x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
                                     C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                     C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ubyte))]
    x.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                             C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
    x.XFree.argtypes = [C.c_void_p]
    x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
    x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
    x.XFlush.argtypes = [C.c_void_p]
    x.XCloseDisplay.argtypes = [C.c_void_p]
    t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
    display = x.XOpenDisplay(display_name.encode())
    if not display:
        raise RuntimeError("Cannot open the private test display")
    x_errors = []
    handler_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)
    # Windows can vanish between query and use (GTK4 recreates surfaces); count, don't exit.
    on_x_error = handler_type(lambda _display, _event: x_errors.append(1) or 0)
    x.XSetErrorHandler.argtypes = [handler_type]
    x.XSetErrorHandler(on_x_error)

    class Attributes(C.Structure):
        _fields_ = [("x", C.c_int), ("y", C.c_int), ("width", C.c_int), ("height", C.c_int),
                    ("border_width", C.c_int), ("depth", C.c_int), ("visual", C.c_void_p), ("root", C.c_ulong),
                    ("class_", C.c_int), ("bit_gravity", C.c_int), ("win_gravity", C.c_int),
                    ("backing_store", C.c_int), ("backing_planes", C.c_ulong), ("backing_pixel", C.c_ulong),
                    ("save_under", C.c_int), ("colormap", C.c_ulong), ("map_installed", C.c_int),
                    ("map_state", C.c_int), ("padding", C.c_long * 16)]
    x.XGetWindowAttributes.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(Attributes)]

    def area(window):
        """Visible size in pixels; 0 if unmapped. Picks the main toplevel, not popups."""
        attributes = Attributes()
        if not x.XGetWindowAttributes(display, window, C.byref(attributes)) or attributes.map_state != 2:
            return 0
        return attributes.width * attributes.height

    def pid_of(window):
        actual, fmt, count, rest = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
        data = C.POINTER(C.c_ubyte)()
        x.XGetWindowProperty(display, window, x.XInternAtom(display, b"_NET_WM_PID", False), 0, 1, False, 0,
                             C.byref(actual), C.byref(fmt), C.byref(count), C.byref(rest), C.byref(data))
        try:
            return C.cast(data, C.POINTER(C.c_ulong))[0] if data and fmt.value == 32 and count.value else None
        finally:
            if data:
                x.XFree(data)

    try:
        def main_window(deadline_seconds=20):
            deadline_at = time.monotonic() + deadline_seconds
            while True:
                root, parent, children, count = C.c_ulong(), C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
                x.XQueryTree(display, x.XDefaultRootWindow(display), C.byref(root), C.byref(parent),
                             C.byref(children), C.byref(count))
                candidates = [children[i] for i in range(count.value)]
                if children:
                    x.XFree(children)
                owned = [(area(w), w) for w in candidates if pid_of(w) == pid]
                owned = [item for item in owned if item[0] >= 200 * 100]
                if owned:
                    return max(owned)[1]
                if not Path(f"/proc/{pid}").exists():
                    raise RuntimeError("ptyxis exited")
                if time.monotonic() > deadline_at:
                    raise RuntimeError("ptyxis window never mapped on the test display")
                time.sleep(0.2)

        window = main_window()
        time.sleep(3)  # shell start: the user's ~/.bashrc (nvm, plugin) loads
        print(f"WINDOW {window} area={area(window)}", flush=True)
        activate(x, display, window)

        x.XGetInputFocus.argtypes = [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]

        def focus_owned():
            # Keyboard focus must sit in a window of the launched ptyxis process.
            focus, revert = C.c_ulong(), C.c_int()
            x.XGetInputFocus(display, C.byref(focus), C.byref(revert))
            candidate = focus.value
            for _level in range(16):
                if candidate <= 1:
                    return False
                if pid_of(candidate) == pid:
                    return True
                root, parent, children, count = C.c_ulong(), C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
                if not x.XQueryTree(display, candidate, C.byref(root), C.byref(parent), C.byref(children),
                                    C.byref(count)):
                    return False
                if children:
                    x.XFree(children)
                if not parent.value or parent.value == candidate:
                    return False
                candidate = parent.value
            return False

        sent = [0]
        refocused = [0]

        def send(text):
            shift_code = x.XKeysymToKeycode(display, x.XStringToKeysym(b"Shift_L"))
            for char in text:
                if not focus_owned():
                    refocused[0] += 1
                    try:
                        activate(x, display, main_window(5))
                    except RuntimeError as error:
                        raise RuntimeError(f"{error} after {sent[0]} keys of {text!r}") from error
                if not focus_owned():
                    focus, revert = C.c_ulong(), C.c_int()
                    x.XGetInputFocus(display, C.byref(focus), C.byref(revert))
                    raise RuntimeError(f"Focus left ptyxis; stopped before injecting a key "
                                       f"(focus={focus.value} pid={pid_of(focus.value) if focus.value > 1 else None} "
                                       f"target={window} ptyxis_pid={pid} keys_sent={sent[0]} "
                                       f"refocused={refocused[0]})")
                code = x.XKeysymToKeycode(display, x.XStringToKeysym(NAMES.get(char, char).encode()))
                if not code:
                    raise RuntimeError(f"Test key unavailable: {char!r}")
                shift = char in SHIFTED
                if shift:
                    t.XTestFakeKeyEvent(display, shift_code, True, 0)
                t.XTestFakeKeyEvent(display, code, True, 0)
                t.XTestFakeKeyEvent(display, code, False, 0)
                if shift:
                    t.XTestFakeKeyEvent(display, shift_code, False, 0)
                x.XFlush(display)
                sent[0] += 1
                time.sleep(0.03)

        out = str(OUT)
        send(f'echo "tieengs vieetj" > {out}\n')
        time.sleep(0.6)
        send(f"read -s -r p; [ \"$p\" = as ] && echo SAME >> {out} || echo DIFF >> {out}; unset p\n")
        time.sleep(0.6)
        send("as\n")
        until = time.monotonic() + 5
        def written():
            return OUT.read_text().splitlines() if OUT.exists() else []
        while time.monotonic() < until and len(written()) < 2:
            time.sleep(0.1)
        lines = written()
        if lines[:1] != ["tiếng việt"]:
            raise AssertionError(f"bash in ptyxis received {lines[:1]!r} for the quoted phrase, expected 'tiếng việt'")
        if lines[1:2] != ["SAME"]:
            raise AssertionError(f"Secret typed with ECHO off: shell verdict {lines[1:2]!r}, expected SAME")
        print("PASS ptyxis app (user's ~/.bashrc): quoted Telex reached bash as 'tiếng việt'; "
              f"ECHO-off secret reached the shell unchanged. (surface refocus={refocused[0]}, x_errors={len(x_errors)})")
        return 0
    finally:
        x.XCloseDisplay(display)


if __name__ == "__main__":
    try:
        status = main()
    except (OSError, RuntimeError, AssertionError, ValueError) as error:
        print(f"PTYXIS FAILED: {error}")
        status = 1
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
