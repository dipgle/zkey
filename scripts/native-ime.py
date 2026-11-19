#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install / remove the NATIVE (Rust) zkey engine as the user's IBus input source, reversibly.

enable:
  1. refuse unless native/target/release/zkey-native attests the CURRENT source (provenance)
  2. copy it to ~/.local/lib/zkey-native/zkey-native
  3. write ~/.local/share/ibus/component/zkey-native.xml (exec = that binary, --ibus
     --experimental-rewrite: without the flag the engine only passes keys through)
  4. move ~/.cache/ibus/bus/registry aside (a cache older than the component directory never
     lists the engine: measured 18/11) so ibus-daemon rebuilds it
  5. GNOME input sources: replace ('ibus','zkey') by ('ibus','zkey-native') (original saved)
  6. `ibus restart`, then wait until the running daemon LISTS the engine (not just "restarted")
`enable --trace` also logs engine events (metadata only) to ~/.local/state/zkey-native-ime/engine-trace.log.
disable restores the sources, removes only files whose SHA-256 still matches, moves the cache
aside again and restarts ibus. State is written BEFORE any change, so disable can always undo.
ZKEY_SKIP_GSETTINGS=1 / ZKEY_SKIP_IBUS=1 skip steps 5 / 6 (unit tests).
Exit 0 done, 1 refused/red (message says why), 2 cannot run/measure.
"""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ("ibus", "zkey-native")
PYTHON_SOURCE = ("ibus", "zkey")
COMPONENT_NAME = "org.freedesktop.IBus.ZkeyNative"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def system_ime():
    return load("system_ime", "scripts/system-ime.py")


def paths():
    home = Path(os.environ.get("HOME", str(Path.home())))
    return {"home": home, "lib": home / ".local/lib/zkey-native",
            "binary": home / ".local/lib/zkey-native/zkey-native",
            "component": home / ".local/share/ibus/component/zkey-native.xml",
            "cache": home / ".cache/ibus/bus/registry",
            "state": home / ".local/state/zkey-native-ime"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attest(binary):
    """Source attestation of the built binary; raises when it is stale or unverifiable."""
    sys.path.insert(0, str(ROOT / "native/tests"))
    try:
        from provenance import verify
        return verify(binary)
    finally:
        sys.path.remove(str(ROOT / "native/tests"))


def component_xml(binary, trace_log=None):
    """`trace_log`: run the engine through `sh -c exec env ZKEY_NATIVE_TRACE=1 … 2>> log`. ibus-daemon
    discards a child's stderr, so this is the only way to see which clients the engine accepts.
    The trace holds metadata only (event names, protected flag, purpose number), never keys or text."""
    from xml.sax.saxutils import escape
    command = f"{binary} --ibus --experimental-rewrite"
    if trace_log:
        command = f'/bin/sh -c "exec env ZKEY_NATIVE_TRACE=1 {command} 2>> {trace_log}"'
    return ('<?xml version="1.0" encoding="utf-8"?>\n<component>\n'
            f"  <name>{COMPONENT_NAME}</name>\n  <description>zkey native Telex</description>\n"
            "  <version>0.2.0-dev</version>\n  <license>AGPL-3.0-or-later</license>\n"
            "  <author>zkey contributors</author>\n"
            f"  <exec>{escape(command)}</exec>\n"
            "  <textdomain>zkey-native</textdomain>\n  <engines>\n    <engine>\n"
            "      <name>zkey-native</name>\n      <longname>zkey native</longname>\n"
            "      <description>Vietnamese Telex (native Rust)</description>\n      <language>vi</language>\n"
            "      <license>AGPL-3.0-or-later</license>\n      <author>zkey contributors</author>\n"
            "      <icon>input-keyboard</icon>\n      <layout>us</layout>\n      <symbol>Z</symbol>\n"
            "    </engine>\n  </engines>\n</component>\n")


def gsettings(module, *args):
    return module.gsettings(*args)


def restart_and_wait(module, want_engine, timeout=25):
    """`ibus restart`, then poll the RUNNING daemon until it does (want_engine) or does not list zkey-native."""
    if os.environ.get("ZKEY_SKIP_IBUS") == "1":
        return True
    address = module.daemon_address()
    if address is None:
        print("NOT MEASURABLE: no running ibus-daemon address; restart ibus yourself, then run verify")
        return None
    result = subprocess.run(["ibus", "restart"], capture_output=True, text=True, timeout=20,
                            env={**os.environ, "IBUS_ADDRESS": address})
    if result.returncode:
        print(f"ibus restart failed (exit {result.returncode})")
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1)
        names = module.engine_names()
        if names is not None and ("zkey-native" in names) == want_engine:
            return True
    return False


def enable():
    p = paths()
    state_file = p["state"] / "state.json"
    if state_file.exists():
        print(f"REFUSED: already enabled (state {state_file}); run disable first")
        return 1
    if p["component"].exists() or p["binary"].exists():
        print("REFUSED: zkey-native files exist that this tool did not install")
        return 1
    source = ROOT / "native/target/release/zkey-native"
    try:
        attest(source)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"REFUSED: native binary does not attest the current source: {error}")
        return 1
    module = system_ime()
    state = {"sources": gsettings(module, "get", "org.gnome.desktop.input-sources", "sources"),
             "binary_sha256": digest(source), "cache_backup": None}
    p["state"].mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state) + "\n")  # BEFORE any change
    p["lib"].mkdir(parents=True, exist_ok=True)
    temporary = p["binary"].with_suffix(".new")
    shutil.copy2(source, temporary)
    temporary.chmod(0o755)
    temporary.rename(p["binary"])
    p["component"].parent.mkdir(parents=True, exist_ok=True)
    trace_log = p["state"] / "engine-trace.log" if "--trace" in sys.argv[2:] else None
    state["trace_log"] = str(trace_log) if trace_log else None
    p["component"].write_text(component_xml(p["binary"], trace_log))
    state["component_sha256"] = digest(p["component"])
    if p["cache"].exists():
        backup = p["cache"].with_name(f"registry.zkey-bak-{int(time.time())}")
        p["cache"].rename(backup)
        state["cache_backup"] = backup.name
    state_file.write_text(json.dumps(state) + "\n")
    if state["sources"] is not None:
        current = ast.literal_eval(state["sources"].removeprefix("@a(ss) "))
        updated = [NATIVE if item == PYTHON_SOURCE else item for item in current]
        if NATIVE not in updated:
            updated.append(NATIVE)
        gsettings(module, "set", "org.gnome.desktop.input-sources", "sources", repr(updated))
    ok = restart_and_wait(module, True)
    if ok:
        print("ENABLED: running ibus-daemon lists engine zkey-native; choose it with Super+Space. Undo: native-ime.py disable")
        return 0
    if ok is None:
        return 2
    print("RED: ibus restarted (or could not) but the daemon does not list zkey-native; run `native-ime.py disable`")
    return 1


def disable():
    p = paths()
    state_file = p["state"] / "state.json"
    if not state_file.is_file():
        print("NOTHING TO DO: zkey native was not enabled by this tool")
        return 1
    state = json.loads(state_file.read_text())
    module = system_ime()
    if state["sources"] is not None:
        gsettings(module, "set", "org.gnome.desktop.input-sources", "sources", state["sources"].removeprefix("@a(ss) "))
    kept = []
    if p["component"].is_file():
        if digest(p["component"]) == state.get("component_sha256"):
            p["component"].unlink()
        else:
            kept.append(str(p["component"]))
    if p["binary"].is_file():
        if digest(p["binary"]) == state["binary_sha256"]:
            p["binary"].unlink()
        else:
            kept.append(str(p["binary"]))
    if p["cache"].exists():  # lists the removed engine: make the daemon rebuild it
        p["cache"].rename(p["cache"].with_name(f"registry.zkey-removed-{int(time.time())}"))
    state_file.unlink()
    for directory in (p["state"], p["lib"]):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    ok = restart_and_wait(module, False)
    print("DISABLED: sources restored, component and binary removed" + (f"; KEPT edited files: {kept}" if kept else "")
          + ("" if ok else "; ibus did not confirm the engine is gone (restart it or log in again)"))
    return 0 if ok is not False and not kept else 1


def status():
    p = paths()
    module = system_ime()
    names = module.engine_names()
    print(f"enabled-by-this-tool: {(p['state'] / 'state.json').is_file()}")
    print(f"binary: {'present' if p['binary'].is_file() else 'absent'}  component: {'present' if p['component'].is_file() else 'absent'}")
    print(f"running ibus-daemon lists zkey-native: {'NOT MEASURED' if names is None else 'zkey-native' in names}")
    return 0


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        return {"status": status, "enable": enable, "disable": disable}[action]()
    except KeyError:
        print("usage: native-ime.py [status|enable|disable]")
        return 2
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as error:
        print(f"CANNOT RUN: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
