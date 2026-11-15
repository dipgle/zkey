#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""User-local install / uninstall of zkey (no root, no system input change).

Installs into PREFIX (default ~/.local): bin/zkey, lib/zkey/** (Python engine +
launcher, Rust core, zkey-line, shell plugin), share/applications/zkey.desktop.
The IBus component (system input source path) is NOT installed unless
--with-ibus-component: that path also needs IBUS_ENABLE_SYNC_MODE for the
user session (docs/verification.md 15/11 16:50) and is the owner's decision.

Every installed file is recorded with its SHA-256 in lib/zkey/MANIFEST.json.
Install refuses to overwrite a file it did not install. Uninstall removes only
recorded files still byte-identical; edited files are kept and reported.
Does not edit ~/.bashrc (see scripts/install-shell.sh).
Exit: 0 done, 1 refused/partial (message says what), 2 cannot run.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MANIFEST = Path("lib/zkey/MANIFEST.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_manifest(prefix):
    path = prefix / MANIFEST
    return json.loads(path.read_text()) if path.is_file() else {}


def install(prefix, with_component=False):
    from stage import stage
    prefix = Path(prefix).expanduser().resolve()
    previous = read_manifest(prefix)
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="install-stage-", dir=ROOT / ".tmp") as temporary:
        staged = Path(temporary)
        stage(staged, prefix)
        files = sorted(p for p in staged.rglob("*") if p.is_file())
        if not with_component:
            files = [p for p in files if p.relative_to(staged).parts[:3] != ("share", "ibus", "component")]
        foreign = []
        for source in files:
            relative = source.relative_to(staged).as_posix()
            target = prefix / relative
            if target.exists() and (relative not in previous or digest(target) != previous[relative]):
                foreign.append(relative)
        if foreign:
            print("REFUSED: would overwrite files zkey did not install (or that were edited): "
                  + ", ".join(foreign))
            return 1
        manifest = {}
        for source in files:
            relative = source.relative_to(staged).as_posix()
            target = prefix / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest[relative] = digest(target)
        # Files from an older install that this version no longer ships.
        stale = [r for r in previous if r not in manifest and (prefix / r).is_file() and digest(prefix / r) == previous[r]]
        for relative in stale:
            (prefix / relative).unlink()
        (prefix / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"INSTALLED {len(manifest)} files under {prefix} (manifest {prefix / MANIFEST}); removed {len(stale)} stale.")
    print(f"Run: {prefix / 'bin/zkey'} --run [app]   ·   menu: zkey — Gõ tiếng Việt")
    return 0


def uninstall(prefix):
    prefix = Path(prefix).expanduser().resolve()
    manifest = read_manifest(prefix)
    if not manifest:
        print(f"NOTHING TO DO: no zkey manifest at {prefix / MANIFEST}")
        return 1
    kept = []
    for relative, expected in sorted(manifest.items()):
        target = prefix / relative
        if not target.is_file():
            continue
        if digest(target) != expected:
            kept.append(relative)
            continue
        target.unlink()
    if kept:
        print("KEPT (edited since install): " + ", ".join(kept))
        (prefix / MANIFEST).write_text(json.dumps({r: manifest[r] for r in kept}, indent=1, sort_keys=True) + "\n")
    else:
        (prefix / MANIFEST).unlink()
    # State zkey itself generates inside its own lib dir while running: engine
    # logs (no typed text) and bytecode. Not user data; not in the manifest.
    for generated in ("lib/zkey/.tmp", "lib/zkey/zkey/__pycache__"):
        if (prefix / generated).is_dir() and not kept:
            shutil.rmtree(prefix / generated)
    # Remove only directories that are now empty and were created for zkey.
    for directory in sorted({(prefix / r).parent for r in manifest} | {prefix / "lib/zkey"},
                            key=lambda p: len(p.parts), reverse=True):
        current = directory
        while current != prefix and current.is_dir() and not any(current.iterdir()):
            current.rmdir()
            current = current.parent
    print(f"UNINSTALLED {len(manifest) - len(kept)} files from {prefix}; kept {len(kept)}.")
    return 1 if kept else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--with-ibus-component", action="store_true")
    args = parser.parse_args()
    try:
        return uninstall(args.prefix) if args.uninstall else install(args.prefix, args.with_ibus_component)
    except (OSError, ValueError) as error:
        print(f"CANNOT RUN: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
