#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""System-input-method path, measured without touching the desktop.

What `system-ime.py enable` relies on, end to end on a private Xvfb + private
D-Bus + a private ibus-daemon (NOT the session's IBus/fcitx5):
  - an install made by install-user.py --with-ibus-component (prefix in .tmp)
  - ibus-daemon finds share/ibus/component/zkey.xml via IBUS_COMPONENT_PATH
  - selecting engine "zkey" makes the DAEMON start <prefix>/bin/zkey --ibus
  - real XTest keys into a GTK3 entry (IBUS_ENABLE_SYNC_MODE=1, as enable sets)
ZKEY_PROBE_NO_COMPONENT=1 = reverse control (component dir left out => RED).
Exit 0 pass, 1 fail, 2 not measurable; ends GATE_EXIT.
"""
from pathlib import Path
import ctypes as C
import contextlib
import importlib.util
import io
import os
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402  (never dbus-run-session directly)


def inside():
    spec = importlib.util.spec_from_file_location("install_user", ROOT / "scripts/install-user.py")
    install_user = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(install_user)
    scratch = Path(tempfile.mkdtemp(prefix="sysime-", dir=ROOT / ".tmp"))
    prefix = scratch / "prefix"
    with contextlib.redirect_stdout(io.StringIO()):
        if install_user.install(prefix, with_component=True):
            print("NOT_MEASURABLE: install with component failed")
            return 2
    for name in ("config", "cache", "data"):
        (scratch / name).mkdir()
    address = f"unix:path={scratch}/ibus.sock"
    components = "/nonexistent" if os.environ.get("ZKEY_PROBE_NO_COMPONENT") == "1" else str(prefix / "share/ibus/component")
    env = dict(os.environ, IBUS_ADDRESS=address, IBUS_COMPONENT_PATH=components,
               XDG_CONFIG_HOME=str(scratch / "config"), XDG_CACHE_HOME=str(scratch / "cache"),
               XDG_DATA_HOME=str(scratch / "data"), ZKEY_TRACE="1", GSETTINGS_BACKEND="memory")
    env.pop("IBUS_USE_PORTAL", None)
    log = (scratch / "daemon.log").open("w")
    daemon = subprocess.Popen(["ibus-daemon", "--panel=disable", "--config=disable", "--emoji-extension=disable",
                               "--cache=none", f"--address={address}"], env=env, stdout=log, stderr=log,
                              start_new_session=True)
    try:
        deadline = time.monotonic() + 8
        while not (scratch / "ibus.sock").exists():
            if daemon.poll() is not None or time.monotonic() > deadline:
                print(f"NOT_MEASURABLE: private ibus-daemon did not start ({scratch / 'daemon.log'})")
                return 2
            time.sleep(0.02)
        os.environ.update(IBUS_ADDRESS=address, GTK_IM_MODULE="ibus", IBUS_ENABLE_SYNC_MODE="1")
        import gi
        gi.require_version("IBus", "1.0")
        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11, GLib, Gtk, IBus
        IBus.init()
        bus = IBus.Bus.new()
        deadline = time.monotonic() + 5
        while not bus.is_connected() and time.monotonic() < deadline:
            time.sleep(0.05)
        names = [engine.get_name() for engine in bus.list_engines()]
        if "zkey" not in names:
            print(f"SYSTEM-IME FAILED: ibus-daemon does not list engine zkey (IBUS_COMPONENT_PATH={components}; "
                  f"{len(names)} engines listed)")
            return 1
        if not bus.set_global_engine("zkey"):
            print("SYSTEM-IME FAILED: daemon refused to select zkey")
            return 1
        expected = str(prefix / "bin/zkey")
        started = ""
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not started:
            result = subprocess.run(["pgrep", "-af", f"{expected} --ibus"], capture_output=True, text=True)
            started = result.stdout.strip()
            time.sleep(0.1)
        if not started:
            print(f"SYSTEM-IME FAILED: daemon did not start {expected} --ibus from the component")
            return 1
        if not Gtk.init_check([])[0]:
            print("NOT_MEASURABLE: no X display")
            return 2
        context = GLib.MainContext.default()

        def pump(seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while context.pending():
                    context.iteration(False)
                time.sleep(0.003)
        window = Gtk.Window(title="zkey system IME probe (dữ liệu giả)")
        entry = Gtk.Entry()
        window.add(entry)
        window.show_all()
        pump(0.4)
        x = C.CDLL("libX11.so.6")
        t = C.CDLL("libXtst.so.6")
        x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
        x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        x.XFlush.argtypes = [C.c_void_p]
        x.XSync.argtypes = [C.c_void_p, C.c_int]
        t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        display = x.XOpenDisplay(os.environ["DISPLAY"].encode())
        x.XSetInputFocus(display, GdkX11.X11Window.get_xid(window.get_window()), 2, 0)
        x.XSync(display, False)
        entry.grab_focus()
        pump(0.4)
        trail = []
        for name in ["t", "i", "e", "e", "n", "g", "s", "space", "BackSpace", "BackSpace"]:
            code = x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode()))
            t.XTestFakeKeyEvent(display, code, True, 0)
            t.XTestFakeKeyEvent(display, code, False, 0)
            x.XFlush(display)
            pump(0.15)
            trail.append(entry.get_text())
        window.destroy()
        want = ["t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng", "tiếng ", "tiếng", "tiến"]
        print(f"PROBE: {' '.join(repr(s) for s in trail)}")
        if trail != want:
            print(f"SYSTEM-IME FAILED: typed through the daemon-started engine: {trail} != {want}")
            return 1
        print(f"PASS system-IME path: daemon found zkey.xml via IBUS_COMPONENT_PATH, started {expected} --ibus; "
              f"GTK3 per-key Telex + Backspace correct (sync mode).")
        return 0
    finally:
        if daemon.poll() is None:
            os.killpg(daemon.pid, signal.SIGTERM)
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(daemon.pid, signal.SIGKILL)
        subprocess.run(["pkill", "-f", f"{prefix}/bin/zkey --ibus"], capture_output=True)
        log.close()


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
    env.update(DISPLAY=display, GDK_BACKEND="x11", NO_AT_BRIDGE="1", GIO_USE_VFS="local")
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), "--inside"], env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
