#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Browser acceptance (P0-001 items 1-2): real Firefox, real XTest keys.

Private Xvfb (ZKEY_TEST_DISPLAY) + private D-Bus + private IBus with zkey; a
fresh throwaway profile under zkey/.tmp; never the user's browser or desktop.
The page (scripts/fixtures/browser-input.html) reports what IT received —
field values, input events, IME composition events — in document.title,
read here from the X11 window title. No DOM injection, no remote protocol.
Synthetic data only. Exit 0 pass, 1 fail, 2 not measurable; ends GATE_EXIT.
"""
from pathlib import Path
import ctypes as C
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PAGE = ROOT / "scripts/fixtures/browser-input.html"
MARK = "zkey-browser-probe|"
PREFS = """user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.aboutwelcome.enabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("app.update.auto", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("signon.rememberSignons", false);
user_pref("browser.formfill.enable", false);
"""


def x11():
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
    x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
    x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
    x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
    x.XFlush.argtypes = [C.c_void_p]
    x.XSync.argtypes = [C.c_void_p, C.c_int]
    x.XCloseDisplay.argtypes = [C.c_void_p]
    t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
    return x, t


def inside():
    from zkey.runtime import isolated_engine
    # ZKEY_FIREFOX: a non-snap build (e.g. official tarball under .tmp/tools); default = system firefox.
    firefox = os.environ.get("ZKEY_FIREFOX") or shutil.which("firefox")
    snap = not os.environ.get("ZKEY_FIREFOX") and Path("/snap/bin/firefox").exists()
    if not firefox or not PAGE.exists():
        print("NOT_MEASURABLE: firefox or the fixture page is missing")
        return 2
    x, t = x11()
    display = x.XOpenDisplay(os.environ["DISPLAY"].encode())
    if not display:
        print("NOT_MEASURABLE: private X display unavailable")
        return 2
    root = x.XDefaultRootWindow(display)
    utf8 = x.XInternAtom(display, b"UTF8_STRING", False)
    net_name = x.XInternAtom(display, b"_NET_WM_NAME", False)

    def title(window):
        actual, fmt, count, remaining = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
        data = C.POINTER(C.c_ubyte)()
        if x.XGetWindowProperty(display, window, net_name, 0, 65536, False, utf8, C.byref(actual), C.byref(fmt),
                                C.byref(count), C.byref(remaining), C.byref(data)) or not data:
            return ""
        try:
            return bytes(data[:count.value]).decode("utf-8", "replace")
        finally:
            x.XFree(data)

    def windows():
        found, stack = [], [root]
        while stack:
            parent, children, count = C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
            node = stack.pop()
            if not x.XQueryTree(display, node, C.byref(C.c_ulong()), C.byref(parent), C.byref(children), C.byref(count)):
                continue
            kids = [children[i] for i in range(count.value)]
            if children:
                x.XFree(children)
            for kid in kids:
                if MARK in title(kid):
                    found.append(kid)
                elif node == root:
                    stack.append(kid)  # one level down: GTK may wrap the toplevel
        return found

    with isolated_engine() as (env, _bus, _children), \
            tempfile.TemporaryDirectory(prefix="ff-profile-", dir=ROOT / ".tmp") as profile:
        Path(profile, "user.js").write_text(PREFS)
        env = dict(env, MOZ_ENABLE_WAYLAND="0", GDK_BACKEND="x11", MOZ_CRASHREPORTER_DISABLE="1")
        env.pop("WAYLAND_DISPLAY", None)
        # Snap confinement needs the real runtime dir (snap cgroup scope and
        # /run/user/UID/doc), as when the user starts Firefox. D-Bus stays the
        # private bus, so input still goes through ibus-portal to private zkey.
        real_runtime = os.environ.get("ZKEY_REAL_RUNTIME_DIR") if snap else None
        if real_runtime:
            env["XDG_RUNTIME_DIR"] = real_runtime
        log = (ROOT / ".tmp/firefox-accept.log").open("w")
        command = [firefox, "--no-remote", "--new-instance", "--kiosk", "--profile", profile, PAGE.as_uri()]
        if snap and real_runtime:
            # snap-confine requires a snap.<name>.<app>-<uuid>.scope cgroup; it
            # normally asks the session bus, which here is private. Same
            # transient scope any launched app gets; removed when it exits.
            import uuid
            command = ["systemd-run", "--user", "--scope", "--quiet",
                       f"--unit=snap.firefox.firefox-{uuid.uuid4()}.scope", *command]
        browser = subprocess.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            deadline, target = time.monotonic() + 60, None
            while time.monotonic() < deadline and target is None:
                if browser.poll() is not None:
                    print(f"NOT_MEASURABLE: firefox exited {browser.returncode}; see .tmp/firefox-accept.log")
                    return 2
                found = windows()
                target = found[0] if found else None
                time.sleep(0.25)
            if target is None:
                print("NOT_MEASURABLE: no Firefox window showing the fixture page within 60 s")
                return 2

            def state():
                name = title(target)
                start = name.find(MARK)
                if start < 0:
                    return None
                raw = name[start + len(MARK):].split(" ", 1)[0].split("—", 1)[0].strip()
                if raw == "start":
                    return None
                try:
                    return json.loads(urllib.parse.unquote(raw))
                except ValueError:
                    return None

            x.XSetInputFocus(display, target, 2, 0)
            x.XSync(display, False)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not ((s := state()) and s["focus"] == "text"):
                time.sleep(0.1)
            if not (s := state()) or s["focus"] != "text":
                print(f"NOT_MEASURABLE: page did not report focus in the text field ({s})")
                return 2

            def send(name):
                code = x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode()))
                if not code:
                    raise RuntimeError(f"Test key {name} unavailable")
                t.XTestFakeKeyEvent(display, code, True, 0)
                t.XTestFakeKeyEvent(display, code, False, 0)
                x.XFlush(display)

            def expect(field, want, seconds=4):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    s = state()
                    if s and s[field] == want:
                        return s
                    time.sleep(0.02)
                raise AssertionError(f"page field {field}: expected={want!r}, actual={(state() or {}).get(field)!r}")

            for key, want in zip("tieengs", ("t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng")):
                send(key)
                expect("text", want)
                time.sleep(0.06)
            for key in ["space", *"vieetj"]:
                send(key)
                time.sleep(0.06)
            expect("text", "tiếng việt")
            send("BackSpace")
            expect("text", "tiếng việ")
            send("t")
            s = expect("text", "tiếng việt")
            send("Tab")
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and (state() or {}).get("focus") != "secret":
                time.sleep(0.05)
            if (state() or {}).get("focus") != "secret":
                raise AssertionError("Tab did not move focus to the password field")
            for key in "aas":  # Telex would make "ấ"; password must stay as typed
                send(key)
                time.sleep(0.08)
            s = expect("secret", "aas")
            time.sleep(0.3)
            s = state()
            if s["compText"] or s["compSecret"]:
                raise AssertionError(f"IME composition reached the page: text={s['compText']}, password={s['compSecret']}")
            engine_log = ROOT / ".tmp" / (Path(env["IBUS_ADDRESS"].split("unix:path=", 1)[1]).parent.name + ".log")
            seen = engine_log.read_text().count("key-state ")
            if seen < len("tieengs"):
                raise AssertionError(f"Wrong input engine: private zkey saw only {seen} key calls")
            print(f"PASS Firefox: 7 per-key prefixes in the page's own value; 'tiếng việt'; Backspace; password "
                  f"'aas' unchanged; 0 composition events (text, password); {s['inputs']} input events; "
                  f"engine saw {seen} keys.")
            return 0
        finally:
            if browser.poll() is None:
                os.killpg(browser.pid, signal.SIGTERM)
                try:
                    browser.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(browser.pid, signal.SIGKILL)
                    browser.wait()
            log.close()
            x.XCloseDisplay(display)


def main():
    if sys.argv[1:] == ["--inside"]:
        try:
            return inside()
        except AssertionError as error:
            print(f"FIREFOX FAILED: {error}")
            return 1
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
               GIO_USE_VFS="local", ZKEY_TRACE="1", ZKEY_REAL_RUNTIME_DIR=f"/run/user/{os.getuid()}")
    # The private bus daemon must never see the real runtime dir: a service it
    # activates (xdg-document-portal) would lazily unmount and replace the
    # desktop's /run/user/UID/doc (happened 15/11 20:1x in a manual probe).
    # Only the browser process gets the real one (ZKEY_REAL_RUNTIME_DIR).
    with tempfile.TemporaryDirectory(prefix="bus-runtime-", dir=ROOT / ".tmp") as bus_runtime:
        os.chmod(bus_runtime, 0o700)
        env["XDG_RUNTIME_DIR"] = bus_runtime
        return subprocess.call(["dbus-run-session", "--", sys.executable, str(Path(__file__).resolve()), "--inside"],
                               env=env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
