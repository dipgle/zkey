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
WORD = "tieengs"
EXPECTED = "tiếng"
SKIP_ENGINE = os.environ.get("ZKEY_INSTALLED_SKIP_ENGINE") == "1"


def free_display():
    for number in range(90, 100):
        if not Path(f"/tmp/.X11-unix/X{number}").exists():
            return f":{number}"
    return None


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

    display_name = free_display()
    if display_name is None:
        return not_measurable("no free X display number")
    xvfb = subprocess.Popen(
        [str(ROOT / ".tmp/tools/root/usr/bin/Xvfb"), display_name,
         "-screen", "0", "900x600x24", "-nolisten", "tcp", "-ac"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.8)
        env = {**os.environ, "DISPLAY": display_name, "IBUS_ADDRESS": address,
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
        display = x.XOpenDisplay(display_name.encode())
        if not display:
            return not_measurable("cannot open private X display")
        window.get_window()
        x.XSetInputFocus(display, window.get_window().get_xid(), 1, 0)
        x.XFlush(display)
        pump(0.4)
        def send(name, pause=0.12):
            code = x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode()))
            t.XTestFakeKeyEvent(display, code, True, 0)
            t.XTestFakeKeyEvent(display, code, False, 0)
            x.XFlush(display)
            pump(pause)

        def clear():
            ctrl = x.XKeysymToKeycode(display, x.XStringToKeysym(b"Control_L"))
            t.XTestFakeKeyEvent(display, ctrl, True, 0)
            x.XFlush(display)
            send("a")
            t.XTestFakeKeyEvent(display, ctrl, False, 0)
            x.XFlush(display)
            send("BackSpace")

        for char in WORD:
            send(char)
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
        else:
            print("FAIL installed-engine GTK3: installed engine did not compose in a real Entry")
            print("GATE_EXIT=1")
            return 1
        # Hà 20/11/21: a word already committed, the separator deleted, then another mark
        # must finish that word (seed from surrounding text). Measured against the INSTALLED
        # engine: the build being green says nothing about what the user is running.
        clear()
        for key in "sawc":
            send(key)
        send("space")
        send("BackSpace")
        send("s")
        pump(0.4)
        seeded = entry.get_text()
        print(f"RESULT separator entry={seeded!r} expected='sắc'")
        # Reverse control in the same run: with the separator still there the mark must start
        # a new word instead of editing the committed one.
        clear()
        for key in "sawc":
            send(key)
        send("space")
        send("s")
        pump(0.4)
        separate = entry.get_text()
        print(f"RESULT separator-control entry={separate!r} expected='săc s'")
        # Hà 21/11: deleting back several characters (not only the separator) and typing a mark
        # must still finish the word that is on screen.
        clear()
        for key in "laj nhi":
            send("space" if key == " " else key)
        for _ in range(4):
            send("BackSpace")
        send("s")
        pump(0.4)
        deleted_back = entry.get_text()
        print(f"RESULT delete-back entry={deleted_back!r} expected='lá'")
        # Hà 21/11: a word the app put there (pasted / existing document) also takes the mark.
        clear()
        entry.set_text("lạ")
        entry.set_position(-1)
        pump(0.4)
        send("s")
        pump(0.4)
        pasted = entry.get_text()
        print(f"RESULT pasted-word entry={pasted!r} expected='lá'")
        if seeded == "sắc" and separate == "săc s" and deleted_back == "lá" and pasted == "lá":
            print("PASS installed-engine GTK3: separator+seed, multi-delete back, pasted word all take the mark")
            print("GATE_EXIT=0")
            return 0
        print("FAIL installed-engine GTK3: separator/seed/delete-back/pasted scenario wrong on the installed engine")
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
