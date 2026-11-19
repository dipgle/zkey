#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A real GTK3 Entry on a private Xvfb, typing through the INSTALLED IBus engine.

Complements accept_firefox_pattern.py: that one checks the engine's D-Bus contract,
this one checks the client path end to end (GTK IM module -> running daemon ->
installed engine -> Entry text). It never touches the user's display, input source
or documents: the display is a private Xvfb and only a synthetic word is typed.

Exit 0 pass, 1 red, 2 not measurable (no daemon / installed engine / engine not
selected). Reverse control: ZKEY_INSTALLED_SKIP_ENGINE=1 forces a plain GTK IM
module; the typed text must then come out raw and this gate must go RED.
"""
from pathlib import Path
import ctypes as C
import glob
import os
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
DISPLAY = ":81"
WORD = "tieengs"
EXPECTED = "tiếng"
SKIP_ENGINE = os.environ.get("ZKEY_INSTALLED_SKIP_ENGINE") == "1"


def not_measurable(reason):
    print(f"NOT_MEASURABLE: {reason}")
    print("GATE_EXIT=2")
    return 2


def daemon_address():
    env = os.environ.get("IBUS_ADDRESS")
    if env:
        return env
    best = None
    for name in glob.glob(str(Path.home() / ".config/ibus/bus/*")):
        try:
            text = Path(name).read_text(errors="replace")
        except OSError:
            continue
        address = re.search(r"^IBUS_ADDRESS=(\S+)$", text, re.M)
        pid = re.search(r"^IBUS_DAEMON_PID=(\d+)$", text, re.M)
        if not address or not pid or not Path(f"/proc/{pid.group(1)}").exists():
            continue
        socket = address.group(1).removeprefix("unix:path=").split(",")[0].split("guid=")[0]
        if not Path(socket).exists():
            continue
        mtime = Path(name).stat().st_mtime
        if best is None or mtime > best[0]:
            best = (mtime, address.group(1))
    return best[1] if best else None


def main():
    if not (Path.home() / ".local/lib/zkey-native/zkey-native").is_file():
        return not_measurable("native engine is not installed")
    address = daemon_address()
    if not address:
        return not_measurable("no running ibus-daemon address")
    if not SKIP_ENGINE:
        try:
            current = subprocess.run(
                ["ibus", "engine"], capture_output=True, text=True, timeout=10,
                env={**os.environ, "IBUS_ADDRESS": address},
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            return not_measurable(f"cannot ask the daemon for its engine: {error}")
        if current != "zkey-native":
            return not_measurable(f"global engine is {current or 'unknown'!r}, not zkey-native")

    xvfb = subprocess.Popen(
        [str(ROOT / ".tmp/tools/root/usr/bin/Xvfb"), DISPLAY,
         "-screen", "0", "900x600x24", "-nolisten", "tcp", "-ac"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.8)
        env = {**os.environ, "DISPLAY": DISPLAY, "IBUS_ADDRESS": address,
               "XMODIFIERS": "@im=ibus", "GDK_BACKEND": "x11",
               "GTK_IM_MODULE": "gtk-im-context-simple" if SKIP_ENGINE else "ibus"}
        env.pop("XAUTHORITY", None)
        env.pop("WAYLAND_DISPLAY", None)
        os.environ.update({k: env[k] for k in
                           ("DISPLAY", "IBUS_ADDRESS", "GDK_BACKEND", "GTK_IM_MODULE", "XMODIFIERS")})
        os.environ.pop("WAYLAND_DISPLAY", None)

        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib, Gtk

        if not Gtk.init_check([])[0]:
            return not_measurable("cannot open private display")
        window = Gtk.Window(title="zkey installed-engine acceptance")
        entry = Gtk.Entry()
        window.add(entry)
        window.set_default_size(600, 120)
        window.show_all()
        window.present()
        entry.grab_focus()
        context = GLib.MainContext.default()

        def pump(seconds=0.1):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while context.pending():
                    context.iteration(False)
                time.sleep(0.002)

        pump(1.0)
        x = C.CDLL("libX11.so.6")
        t = C.CDLL("libXtst.so.6")
        x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        x.XKeysymToKeycode.argtypes = [C.c_void_p, C.c_ulong]
        x.XFlush.argtypes = [C.c_void_p]
        x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        display = x.XOpenDisplay(DISPLAY.encode())
        if not display:
            return not_measurable("cannot open private X display")
        window.get_window()
        x.XSetInputFocus(display, window.get_window().get_xid(), 1, 0)
        x.XFlush(display)
        pump(0.4)
        for char in WORD:
            code = x.XKeysymToKeycode(display, x.XStringToKeysym(char.encode()))
            t.XTestFakeKeyEvent(display, code, True, 0)
            t.XTestFakeKeyEvent(display, code, False, 0)
            x.XFlush(display)
            pump(0.12)
        pump(0.6)
        text = entry.get_text()
        print(f"RESULT entry={text!r} expected={EXPECTED!r} engine={os.environ['GTK_IM_MODULE']}")
        if SKIP_ENGINE:
            ok = text == WORD
            print(("PASS" if ok else "FAIL") + " reverse control: without the engine the word stays raw")
            print(f"GATE_EXIT={0 if ok else 1}")
            return 0 if ok else 1
        if text == EXPECTED:
            print("PASS installed-engine GTK3: real Entry shows tiếng")
            print("GATE_EXIT=0")
            return 0
        print("FAIL installed-engine GTK3: installed engine did not compose in a real Entry")
        print("GATE_EXIT=1")
        return 1
    finally:
        xvfb.terminate()
        try:
            xvfb.wait(timeout=10)
        except subprocess.TimeoutExpired:
            xvfb.kill()


if __name__ == "__main__":
    raise SystemExit(main())
