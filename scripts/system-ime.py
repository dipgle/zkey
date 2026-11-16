#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepare / enable / disable zkey as the SYSTEM input method (IBus), reversibly.

NOT run by default. `status` only reads. `enable` changes the login session
(takes effect after a REBOOT: with Linger=yes systemd --user and its
environment survive log out, so log out / log in alone keeps the old values):
  1. user-local install WITH the IBus component (scripts/install-user.py)
  2. ~/.config/environment.d/99-zkey.conf: GTK/QT/XMODIFIERS -> ibus,
     IBUS_COMPONENT_PATH (+ ~/.local/share/ibus/component),
     IBUS_ENABLE_SYNC_MODE=1 (GTK4/X11 async loses refused keys with ANY engine,
     measured 15/11 16:50). 99 sorts after 95-fcitx5.conf, so it wins.
  3. ~/.xinputrc -> `run_im ibus` (im-config format)
  4. GNOME input sources: append ('ibus', 'zkey')
  5. fcitx5 XDG autostart -> hidden (user file gets Hidden=true, or a user
     override is created for a system entry). fcitx5 also claims
     org.freedesktop.IBus; started first it makes GNOME's ibus-daemon exit
     ("current session already has an ibus-daemon", measured 16/11) and zkey
     never receives a key even though the environment says ibus.
Every original is saved under ~/.local/state/zkey/system-ime/ first; `disable`
restores each byte-for-byte (or removes what did not exist). Refuses to
enable twice or to overwrite a 99-zkey.conf it did not write.
`verify` only reads: who owns org.freedesktop.IBus, and whether the running
systemd --user manager already has the 99-zkey.conf values.
ZKEY_SKIP_GSETTINGS=1 skips step 4 (tests). Exit 0 ok, 1 refused/red, 2 cannot run/measure.
"""
from pathlib import Path
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ("ibus", "zkey")
FCITX5_AUTOSTART = "org.fcitx.Fcitx5.desktop"


def paths():
    home = Path(os.environ.get("HOME", str(Path.home())))
    return {"home": home, "prefix": home / ".local",
            "env": home / ".config/environment.d/99-zkey.conf",
            "xinputrc": home / ".xinputrc",
            "autostart": home / ".config/autostart" / FCITX5_AUTOSTART,
            "state": home / ".local/state/zkey/system-ime"}


def autostart_active(text):
    """True when an XDG autostart entry would launch fcitx5 at login."""
    keys = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#"))
    command = keys.get("Exec", "").split()
    return (bool(command) and Path(command[0]).name == "fcitx5"
            and keys.get("Hidden", "false").strip() != "true"
            and keys.get("X-GNOME-Autostart-enabled", "true").strip() != "false")


def hidden(text):
    """Same entry with Hidden=true as the first key of [Desktop Entry]."""
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == "[Desktop Entry]":
            lines.insert(index + 1, "Hidden=true\n")
            return "".join(lines)
    raise ValueError("fcitx5 autostart entry has no [Desktop Entry] group")


def system_autostart():
    for directory in (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":"):
        candidate = Path(directory) / "autostart" / FCITX5_AUTOSTART
        if directory and candidate.is_file():
            return candidate  # first match wins, as in the XDG autostart spec
    return None


def autostart_plan(p):
    """(mode, new_text): 'orig' = hide the user's own file, 'created' = new override."""
    user = p["autostart"]
    if user.is_file():
        text = user.read_text()
        return ("orig", hidden(text)) if autostart_active(text) else (None, None)
    system = system_autostart()
    if system and autostart_active(system.read_text()):
        return "created", hidden(system.read_text())
    return None, None


def ibus_owner():
    """Process name owning org.freedesktop.IBus on this session bus; None = unowned or unmeasurable."""
    try:
        result = subprocess.run(["gdbus", "call", "--session", "-d", "org.freedesktop.DBus",
                                 "-o", "/org/freedesktop/DBus", "-m",
                                 "org.freedesktop.DBus.GetConnectionUnixProcessID", "org.freedesktop.IBus"],
                                capture_output=True, text=True, timeout=5)
        match = re.search(r"uint32 (\d+)", result.stdout)
        if result.returncode or not match:
            return None
        return Path(f"/proc/{match.group(1)}/comm").read_text().strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def manager_env():
    """Environment of the running systemd --user manager; None = unmeasurable."""
    try:
        result = subprocess.run(["systemctl", "--user", "show-environment"],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def stale_keys():
    """Keys of 99-zkey.conf the running manager does not have yet; None = unmeasurable.

    environment.d is read only when the user manager starts. With Linger=yes it
    survives log out, so a new login inherits the OLD values (measured 16/11).
    """
    p = paths()
    if not p["env"].is_file():
        return []
    wanted = dict(line.split("=", 1) for line in p["env"].read_text().splitlines()
                  if "=" in line and not line.startswith("#"))
    actual = manager_env()
    if actual is None:
        return None
    return sorted(key for key, value in wanted.items() if actual.get(key) != value)


def env_text(prefix):
    return ("# Written by zkey scripts/system-ime.py enable; removed by disable.\n"
            "GTK_IM_MODULE=ibus\nQT_IM_MODULE=ibus\nXMODIFIERS=@im=ibus\n"
            # Override every key 95-fcitx5.conf sets: Qt >= 6.7 prefers the
            # plural list, SDL has its own; either one alone revives fcitx5.
            "QT_IM_MODULES=ibus\nSDL_IM_MODULE=ibus\n"
            "IBUS_ENABLE_SYNC_MODE=1\n"
            f"IBUS_COMPONENT_PATH=/usr/share/ibus/component:{prefix}/share/ibus/component\n")


def gsettings(*args):
    if os.environ.get("ZKEY_SKIP_GSETTINGS") == "1":
        return None
    result = subprocess.run(["gsettings", *args], capture_output=True, text=True)
    if result.returncode:
        raise OSError(f"gsettings {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def installer():
    spec = importlib.util.spec_from_file_location("install_user", ROOT / "scripts/install-user.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status():
    p = paths()
    sources = gsettings("get", "org.gnome.desktop.input-sources", "sources")
    print(f"enabled-by-zkey: {(p['state'] / 'state.json').is_file()}")
    print(f"{p['xinputrc']}: {p['xinputrc'].read_text().strip().splitlines()[1:2] if p['xinputrc'].is_file() else 'absent'}")
    print(f"{p['env']}: {'present' if p['env'].is_file() else 'absent'}")
    print(f"component: {(p['prefix'] / 'share/ibus/component/zkey.xml').is_file()}")
    print(f"gnome input sources: {sources if sources is not None else 'skipped'}")
    user = p["autostart"]
    print(f"{user}: {('ACTIVE' if autostart_active(user.read_text()) else 'inactive') if user.is_file() else 'absent'}")
    print(f"org.freedesktop.IBus owner: {ibus_owner() or 'NOT MEASURED (unowned or no session bus)'}")
    return 0


def verify():
    owner = ibus_owner()
    stale = stale_keys()
    if stale:
        print(f"RED: running systemd --user still has old {', '.join(stale)}; "
              "it outlives log out when Linger=yes, so reboot (or restart the user manager)")
    if owner is None or stale is None:
        print("NOT MEASURABLE: org.freedesktop.IBus unowned, no session bus, or no systemd --user")
        return 2
    if stale:
        return 1
    if owner != "ibus-daemon":
        print(f"RED: org.freedesktop.IBus is owned by {owner}, not ibus-daemon; zkey receives no keys")
        return 1
    # Necessary, not sufficient: typing must still be measured in a real app.
    print("OK: org.freedesktop.IBus owned by ibus-daemon (typing itself not measured here)")
    return 0


def enable():
    p = paths()
    state_file = p["state"] / "state.json"
    if state_file.exists():
        print(f"REFUSED: already enabled by zkey (state {state_file}); run disable first")
        return 1
    if p["env"].exists():
        print(f"REFUSED: {p['env']} exists and was not written by an active zkey enable")
        return 1
    autostart_mode, autostart_text = autostart_plan(p)  # validates BEFORE anything is written
    p["state"].mkdir(parents=True, exist_ok=True)
    state = {"xinputrc": None, "sources": None, "fcitx5_autostart": autostart_mode}
    if p["xinputrc"].is_file():
        (p["state"] / "xinputrc.orig").write_bytes(p["xinputrc"].read_bytes())
        state["xinputrc"] = "xinputrc.orig"
    if autostart_mode == "orig":
        (p["state"] / "fcitx5-autostart.orig").write_bytes(p["autostart"].read_bytes())
    state["sources"] = gsettings("get", "org.gnome.desktop.input-sources", "sources")
    state_file.write_text(json.dumps(state) + "\n")  # written BEFORE any change: disable can always undo
    if installer().install(p["prefix"], with_component=True):
        print("REFUSED: user-local install failed; nothing else changed")
        state_file.unlink()
        return 1
    p["env"].parent.mkdir(parents=True, exist_ok=True)
    p["env"].write_text(env_text(p["prefix"]))
    p["xinputrc"].write_text("# Written by zkey scripts/system-ime.py enable\nrun_im ibus\n")
    if autostart_mode:
        p["autostart"].parent.mkdir(parents=True, exist_ok=True)
        p["autostart"].write_text(autostart_text)
    if state["sources"] is not None:
        current = ast.literal_eval(state["sources"].removeprefix("@a(ss) "))
        if SOURCE not in current:
            gsettings("set", "org.gnome.desktop.input-sources", "sources", repr(current + [SOURCE]))
    print("ENABLED for the next boot: reboot (log out is not enough with Linger=yes), then system-ime.py verify. Undo: system-ime.py disable")
    return 0


def disable():
    p = paths()
    state_file = p["state"] / "state.json"
    if not state_file.is_file():
        print("NOTHING TO DO: zkey did not enable the system input method")
        return 1
    state = json.loads(state_file.read_text())
    if state["sources"] is not None:
        gsettings("set", "org.gnome.desktop.input-sources", "sources", state["sources"].removeprefix("@a(ss) "))
    if state["xinputrc"]:
        p["xinputrc"].write_bytes((p["state"] / state["xinputrc"]).read_bytes())
        (p["state"] / state["xinputrc"]).unlink()
    elif p["xinputrc"].is_file():
        p["xinputrc"].unlink()
    p["env"].unlink(missing_ok=True)
    # .get: state files written before 16/11 have no autostart key (nothing to undo).
    if state.get("fcitx5_autostart") == "orig":
        p["autostart"].write_bytes((p["state"] / "fcitx5-autostart.orig").read_bytes())
        (p["state"] / "fcitx5-autostart.orig").unlink()
    elif state.get("fcitx5_autostart") == "created":
        p["autostart"].unlink(missing_ok=True)
    component = p["prefix"] / "share/ibus/component/zkey.xml"
    module = installer()
    manifest = module.read_manifest(p["prefix"])
    relative = "share/ibus/component/zkey.xml"
    if component.is_file() and manifest.get(relative) == module.digest(component):
        component.unlink()
        manifest.pop(relative)
        (p["prefix"] / module.MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    state_file.unlink()
    for directory in (p["state"], p["state"].parent, p["env"].parent, p["autostart"].parent):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    print("DISABLED: originals restored; reboot (log out is not enough with Linger=yes). (zkey --run and the user-local install stay.)")
    return 0


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        return {"status": status, "verify": verify, "enable": enable, "disable": disable}[action]()
    except KeyError:
        print("usage: system-ime.py [status|verify|enable|disable]")
        return 2
    except (OSError, ValueError, SyntaxError) as error:
        print(f"CANNOT RUN: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
