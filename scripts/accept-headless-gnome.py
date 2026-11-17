#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fresh-login rehearsal: a HEADLESS GNOME Shell on a private bus, real config copies.

Answers, without rebooting the desk: with the files system-ime.py wrote, does a
NEW login give org.freedesktop.IBus to ibus-daemon (not fcitx5) and does zkey
turn Telex keys into Vietnamese in a GTK4 window?

  python3 scripts/accept-headless-gnome.py [login|control-squatter]

login          environment = systemd's own environment.d generator over a COPY of
               ~/.config/environment.d; fcitx5 starts only if the (copied) XDG
               autostart entry would start it at login (and is installed)
control-squatter  inverse control: another process takes org.freedesktop.IBus
               first, as fcitx5 did on 16/11 => must be RED

Worst-case order, as measured 16/11 10:10: autostart (fcitx5) BEFORE the
ibus-daemon GNOME unit (`ibus-daemon --panel disable`, Type=dbus).
Keys go in through the headless shell's org.gnome.Mutter.RemoteDesktop (the
compositor input path a keyboard uses), not XTest. Synthetic text only.

Isolation: private D-Bus + runtime dir (private_bus.py); XDG_CONFIG/DATA/CACHE/
STATE_HOME are copies/empties under zkey/.tmp, so dconf, ibus and shell state of
the real desktop are never written. Whole run sits in a systemd --user scope
with MemoryMax and low CPUWeight (open 16/09 machine-hang incident).
NOT the real session: a GREEN here is a rehearsal; acceptance is still the
desk after reboot (system-ime.py verify + typing in real apps).
Exit 0 green, 1 red, 2 not measurable.
"""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402  (never dbus-run-session directly)

GENERATOR = "/usr/lib/systemd/user-environment-generators/30-systemd-environment-d-generator"
DISPLAY_NAME = "zkey-headless-0"
TYPED = "Tieengs Vieejt"  # synthetic Telex
WANT = "Tiếng Việt"
MIN_AVAILABLE_MB = 2500
SUPER_L, CONTROL_L, BACKSPACE = 0xFFEB, 0xFFE3, 0xFF08


def system_ime():
    spec = importlib.util.spec_from_file_location("system_ime", ROOT / "scripts/system-ime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def available_mb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0


# ---------------------------------------------------------------- outer side

def sandbox():
    (ROOT / ".tmp").mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="headless-", dir=ROOT / ".tmp"))
    real = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    for name in ("config", "data", "cache", "state"):
        (base / name).mkdir()
    for name in ("environment.d", "autostart", "zkey"):
        if (real / name).is_dir():
            shutil.copytree(real / name, base / "config" / name)
    if (real / "dconf/user").is_file():
        (base / "config/dconf").mkdir()
        shutil.copy2(real / "dconf/user", base / "config/dconf/user")
    return base


def login_env(base):
    """Environment a fresh systemd --user would hand the session (generator output)."""
    home = str(Path.home())
    seed = {"HOME": home, "USER": os.environ.get("USER", ""), "LOGNAME": os.environ.get("LOGNAME", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"), "SHELL": os.environ.get("SHELL", "/bin/bash"),
            "PATH": f"{home}/.local/bin:/usr/local/bin:/usr/bin:/bin",
            "XDG_CONFIG_HOME": str(base / "config"), "XDG_DATA_HOME": str(base / "data"),
            "XDG_CACHE_HOME": str(base / "cache"), "XDG_STATE_HOME": str(base / "state"),
            "XDG_CONFIG_DIRS": "/etc/xdg/xdg-ubuntu:/etc/xdg",
            "XDG_DATA_DIRS": os.environ.get("XDG_DATA_DIRS", "/usr/share/ubuntu:/usr/local/share:/usr/share"),
            "XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_DESKTOP": "ubuntu",
            "DESKTOP_SESSION": "ubuntu", "GNOME_SHELL_SESSION_MODE": "ubuntu", "XDG_SESSION_TYPE": "wayland"}
    result = subprocess.run([GENERATOR], env=seed, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise OSError(f"environment generator failed: {result.stderr.strip()}")
    env = dict(seed)
    env.update(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return env


def autostart_starts_fcitx5(base, module):
    user = base / "config/autostart" / module.FCITX5_AUTOSTART
    entry = user if user.is_file() else module.system_autostart()
    return bool(entry) and module.autostart_active(entry.read_text())


def leftovers(base):
    """PIDs whose environment still points into this sandbox (orphaned services)."""
    marker = str(base).encode()
    found = []
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit() and int(proc.name) != os.getpid():
            try:
                if marker in (proc / "environ").read_bytes():
                    found.append(int(proc.name))
            except OSError:
                pass
    return found


def stop_all(pids):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        time.sleep(1)


def outer(mode):
    if mode not in ("login", "control-squatter"):
        print(f"usage: {Path(__file__).name} [login|control-squatter]")
        return 2
    if available_mb() < MIN_AVAILABLE_MB:
        print(f"NOT MEASURABLE: MemAvailable {available_mb()} MB < {MIN_AVAILABLE_MB} MB; not starting a second shell")
        return 2
    if os.environ.get("ZKEY_HEADLESS_SCOPE") != "1":
        env = dict(os.environ, ZKEY_HEADLESS_SCOPE="1")
        argv = ["systemd-run", "--user", "--scope", "--quiet", "-p", "MemoryMax=2500M",
                "-p", "CPUWeight=30", "--", sys.executable, __file__, mode]
        try:
            return subprocess.run(argv, env=env, timeout=300).returncode
        except subprocess.TimeoutExpired:
            print("NOT MEASURABLE: rehearsal exceeded 300 s")
            return 2
    module = system_ime()
    base = sandbox()
    env = login_env(base)
    fcitx5 = mode == "login" and autostart_starts_fcitx5(base, module) and bool(shutil.which("fcitx5"))
    squatter = mode == "control-squatter"
    keys = ("GTK_IM_MODULE", "QT_IM_MODULE", "QT_IM_MODULES", "SDL_IM_MODULE", "XMODIFIERS")
    print(f"sandbox {base}")
    print("login env: " + " ".join(f"{key}={env.get(key, '-')}" for key in keys))
    print(f"fcitx5 at login: {fcitx5} (autostart entry + installed); IBus squatter: {squatter}")
    first = "fcitx5" if fcitx5 else "squatter" if squatter else "none"
    argv, penv = private_bus.command([sys.executable, __file__, "--inside", str(base), first], env)
    try:
        code = subprocess.run(argv, env=penv, timeout=240).returncode
    except subprocess.TimeoutExpired:
        code = 2
        print("NOT MEASURABLE: inside run exceeded 240 s")
    left = leftovers(base)
    if left:
        print(f"cleanup: {len(left)} orphan process(es) from the sandbox stopped: {left}")
        stop_all(left)
    still = leftovers(base)
    for _ in range(10):  # SIGKILLed children may take a moment to be reaped
        if not still:
            break
        time.sleep(1)
        still = leftovers(base)
    if still:
        print(f"RED: processes still alive after cleanup: {still}")
        return 1 if code == 0 else code
    return code


# ---------------------------------------------------------------- inside the private bus

def inside(base, first):
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    base = Path(base)
    conn = Gio.bus_get_sync(Gio.BusType.SESSION)
    children = []
    report = {"first_ibus_claimant": first}

    def spawn(argv, log, extra=None):
        child = subprocess.Popen(argv, env=dict(os.environ, **(extra or {})), stdout=open(base / log, "w"),
                                 stderr=subprocess.STDOUT, start_new_session=True)
        children.append(child)
        return child

    def wait(predicate, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            value = predicate()
            if value:
                return value
            time.sleep(0.2)
        return None

    def owner(name):
        try:
            pid = conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                 "GetConnectionUnixProcessID", GLib.Variant("(s)", (name,)),
                                 GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
            return Path(f"/proc/{pid}/comm").read_text().strip()
        except (GLib.Error, OSError):
            return None

    def finish(code, why):
        report["verdict"] = why
        print(json.dumps(report, ensure_ascii=False))
        (base / "verdict.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(children):
            try:
                child.wait(5)
            except subprocess.TimeoutExpired:
                child.kill()
        return code

    os.environ.pop("DISPLAY", None)
    # DING (Ubuntu desktop icons) crash-loops headless (relaunched every 3 s,
    # pulls Nautilus + Tracker, 17/11 07:09) and has nothing to do with input.
    # gsettings here talks to the PRIVATE bus => dconf-service writes the sandbox copy.
    current = subprocess.run(["gsettings", "get", "org.gnome.shell", "disabled-extensions"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    disabled = [] if current in ("", "@as []") else [item.strip(" '") for item in current.strip("[]").split(",")]
    subprocess.run(["gsettings", "set", "org.gnome.shell", "disabled-extensions",
                    repr(sorted(set(disabled) | {"ding@rastersoft.com"}))], timeout=10, check=False)
    if first == "fcitx5":
        spawn(["fcitx5"], "fcitx5.log")
    elif first == "squatter":
        spawn([sys.executable, __file__, "--squat"], "squatter.log")
    if first != "none":
        report["owner_before_ibus"] = wait(lambda: owner("org.freedesktop.IBus"), 15)
    shell = spawn(["gnome-shell", "--headless", "--wayland", "--no-x11", "--virtual-monitor", "1280x800",
                   "--wayland-display", DISPLAY_NAME], "shell.log")
    if not wait(lambda: owner("org.gnome.Mutter.RemoteDesktop") or shell.poll() is not None, 90) \
            or shell.poll() is not None:
        return finish(2, f"NOT MEASURABLE: headless shell did not come up (exit {shell.poll()}, see shell.log)")
    # The GNOME unit, same command line; with the name taken it exits like on 16/11.
    ibus = spawn(["ibus-daemon", "--panel", "disable"], "ibus.log")
    wait(lambda: owner("org.freedesktop.IBus") or ibus.poll() is not None, 15)
    report["ibus_daemon_exit"] = ibus.poll()
    report["ibus_owner"] = owner("org.freedesktop.IBus")
    result = base / "app.json"

    def app_state():
        try:
            return json.loads(result.read_text())
        except (OSError, ValueError):
            return None

    try:
        path = None
        for args in (None, GLib.Variant("(a{sv})", ({},))):
            try:
                path = conn.call_sync("org.gnome.Mutter.RemoteDesktop", "/org/gnome/Mutter/RemoteDesktop",
                                      "org.gnome.Mutter.RemoteDesktop", "CreateSession", args, None,
                                      Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
                break
            except GLib.Error as error:
                report["create_session_error"] = error.message
        if not path:
            return finish(2, "NOT MEASURABLE: RemoteDesktop.CreateSession refused")
        session = "org.gnome.Mutter.RemoteDesktop.Session"
        conn.call_sync("org.gnome.Mutter.RemoteDesktop", path, session, "Start", None, None,
                       Gio.DBusCallFlags.NONE, 5000, None)

        def key(keysym, pressed):
            conn.call_sync("org.gnome.Mutter.RemoteDesktop", path, session, "NotifyKeyboardKeysym",
                           GLib.Variant("(ub)", (keysym, pressed)), None, Gio.DBusCallFlags.NONE, 2000, None)

        def tap(keysym):
            key(keysym, True)
            time.sleep(0.02)
            key(keysym, False)
            time.sleep(0.05)

        def type_text(text):
            for char in text:
                tap(ord(char))

        spawn([sys.executable, __file__, "--app", str(result)], "app.log",
              {"WAYLAND_DISPLAY": DISPLAY_NAME, "GDK_BACKEND": "wayland"})
        if not wait(lambda: (app_state() or {}).get("mapped"), 30):
            return finish(2, f"NOT MEASURABLE: GTK4 window never mapped ({app_state()})")
        # Startup may leave the overview up; Escape closes it, as a user would.
        report["focus_steps"] = []
        for step in ("wait", "Escape", "Escape"):
            if step == "Escape":
                tap(0xFF1B)
            report["focus_steps"].append(step)
            if wait(lambda: (app_state() or {}).get("focus"), 8):
                break
        else:
            return finish(2, f"NOT MEASURABLE: GTK4 window never got focus ({app_state()})")

        def clear():
            key(CONTROL_L, True)
            tap(ord("a"))
            key(CONTROL_L, False)
            tap(BACKSPACE)
            time.sleep(0.5)

        # Which input source is active is unknown: probe with "aa" like a user would,
        # switch with Super+Space (the real shortcut) if it stays Latin.
        report["probes"] = []
        for attempt in range(3):
            type_text("aa")
            time.sleep(1)
            seen = (app_state() or {}).get("text")
            report["probes"].append(seen)
            clear()
            if seen == "â":
                break
            key(SUPER_L, True)
            tap(0x20)
            key(SUPER_L, False)
            time.sleep(1.5)
        type_text(TYPED)
        time.sleep(1.5)
        report["typed"] = TYPED
        report["text"] = (app_state() or {}).get("text")
    except GLib.Error as error:
        return finish(2, f"NOT MEASURABLE: RemoteDesktop call failed: {error.message}")
    engine = subprocess.run(["ibus", "engine"], capture_output=True, text=True, timeout=5)
    report["ibus_engine"] = engine.stdout.strip() or engine.stderr.strip()
    report["ibus_owner_end"] = owner("org.freedesktop.IBus")
    if report["ibus_owner_end"] != "ibus-daemon":
        return finish(1, f"RED: org.freedesktop.IBus owned by {report['ibus_owner_end']}, not ibus-daemon")
    if report["text"] != WANT:
        return finish(1, f"RED: typed {TYPED!r}, window shows {report['text']!r}, want {WANT!r}")
    return finish(0, "GREEN: ibus-daemon owns IBus and zkey composed Vietnamese in GTK4 (rehearsal, not the desk)")


# ---------------------------------------------------------------- GTK4 window

def unix_signal(GLib, loop):
    try:
        gi_unix = __import__("gi.repository.GLibUnix", fromlist=["GLibUnix"])
        add = gi_unix.signal_add
    except ImportError:
        add = GLib.unix_signal_add
    add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda *_: loop.quit() or False)


def app(result_path):
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    result = Path(result_path)
    Gtk.init()
    window = Gtk.Window(title="zkey headless rehearsal (synthetic text)")
    window.set_default_size(500, 80)
    entry = Gtk.Entry()
    window.set_child(entry)
    loop = GLib.MainLoop()
    window.connect("close-request", lambda *_: loop.quit() or False)

    def dump():
        part = result.with_suffix(".part")
        part.write_text(json.dumps({"mapped": window.get_mapped(), "focus": window.is_active(),
                                    "text": entry.get_text()}, ensure_ascii=False))
        os.replace(part, result)
        return True

    GLib.timeout_add(100, dump)
    window.present()
    entry.grab_focus()
    signal.signal(signal.SIGTERM, lambda *_: loop.quit())
    unix_signal(GLib, loop)
    loop.run()
    return 0


def squat():
    """Inverse control: own org.freedesktop.IBus like fcitx5's IBus frontend did."""
    from gi.repository import Gio, GLib
    loop = GLib.MainLoop()
    Gio.bus_own_name(Gio.BusType.SESSION, "org.freedesktop.IBus", Gio.BusNameOwnerFlags.NONE,
                     None, None, lambda *_: loop.quit())
    signal.signal(signal.SIGTERM, lambda *_: loop.quit())
    unix_signal(GLib, loop)
    loop.run()
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--squat":
        return squat()
    if len(sys.argv) > 1 and sys.argv[1] == "--app":
        return app(sys.argv[2])
    if len(sys.argv) > 1 and sys.argv[1] == "--inside":
        return inside(sys.argv[2], sys.argv[3])
    try:
        return outer(sys.argv[1] if len(sys.argv) > 1 else "login")
    except (OSError, subprocess.SubprocessError) as error:
        print(f"NOT MEASURABLE: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
