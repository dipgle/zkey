#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepare / enable / disable zkey as the SYSTEM input method (IBus), reversibly.

NOT run by default. `status` only reads. `enable` changes the login session
(takes effect after log out / log in):
  1. user-local install WITH the IBus component (scripts/install-user.py)
  2. ~/.config/environment.d/99-zkey.conf: GTK/QT/XMODIFIERS -> ibus,
     IBUS_COMPONENT_PATH (+ ~/.local/share/ibus/component),
     IBUS_ENABLE_SYNC_MODE=1 (GTK4/X11 async loses refused keys with ANY engine,
     measured 15/11 16:50). 99 sorts after 95-fcitx5.conf, so it wins.
  3. ~/.xinputrc -> `run_im ibus` (im-config format)
  4. GNOME input sources: append ('ibus', 'zkey')
Every original is saved under ~/.local/state/zkey/system-ime/ first; `disable`
restores each byte-for-byte (or removes what did not exist). Refuses to
enable twice or to overwrite a 99-zkey.conf it did not write.
ZKEY_SKIP_GSETTINGS=1 skips step 4 (tests). Exit 0 ok, 1 refused, 2 cannot run.
"""
from pathlib import Path
import ast
import importlib.util
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ("ibus", "zkey")


def paths():
    home = Path(os.environ.get("HOME", str(Path.home())))
    return {"home": home, "prefix": home / ".local",
            "env": home / ".config/environment.d/99-zkey.conf",
            "xinputrc": home / ".xinputrc",
            "state": home / ".local/state/zkey/system-ime"}


def env_text(prefix):
    return ("# Written by zkey scripts/system-ime.py enable; removed by disable.\n"
            "GTK_IM_MODULE=ibus\nQT_IM_MODULE=ibus\nXMODIFIERS=@im=ibus\n"
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
    p["state"].mkdir(parents=True, exist_ok=True)
    state = {"xinputrc": None, "sources": None}
    if p["xinputrc"].is_file():
        (p["state"] / "xinputrc.orig").write_bytes(p["xinputrc"].read_bytes())
        state["xinputrc"] = "xinputrc.orig"
    state["sources"] = gsettings("get", "org.gnome.desktop.input-sources", "sources")
    state_file.write_text(json.dumps(state) + "\n")  # written BEFORE any change: disable can always undo
    if installer().install(p["prefix"], with_component=True):
        print("REFUSED: user-local install failed; nothing else changed")
        state_file.unlink()
        return 1
    p["env"].parent.mkdir(parents=True, exist_ok=True)
    p["env"].write_text(env_text(p["prefix"]))
    p["xinputrc"].write_text("# Written by zkey scripts/system-ime.py enable\nrun_im ibus\n")
    if state["sources"] is not None:
        current = ast.literal_eval(state["sources"].removeprefix("@a(ss) "))
        if SOURCE not in current:
            gsettings("set", "org.gnome.desktop.input-sources", "sources", repr(current + [SOURCE]))
    print("ENABLED for the next login: log out and back in. Undo: system-ime.py disable")
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
    component = p["prefix"] / "share/ibus/component/zkey.xml"
    module = installer()
    manifest = module.read_manifest(p["prefix"])
    relative = "share/ibus/component/zkey.xml"
    if component.is_file() and manifest.get(relative) == module.digest(component):
        component.unlink()
        manifest.pop(relative)
        (p["prefix"] / module.MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    state_file.unlink()
    for directory in (p["state"], p["state"].parent, p["env"].parent):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    print("DISABLED: originals restored; log out and back in. (zkey --run and the user-local install stay.)")
    return 0


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        return {"status": status, "enable": enable, "disable": disable}[action]()
    except KeyError:
        print("usage: system-ime.py [status|enable|disable]")
        return 2
    except (OSError, ValueError, SyntaxError) as error:
        print(f"CANNOT RUN: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
