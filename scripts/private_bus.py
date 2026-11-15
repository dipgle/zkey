# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ONLY way test harnesses start a private D-Bus session.

A private bus activates desktop services on demand (xdg-desktop-portal,
xdg-document-portal, at-spi). If the bus daemon or its clients carry the real
XDG_RUNTIME_DIR, an activated xdg-document-portal mounts over
/run/user/UID/doc and the DESKTOP's document portal loses its FUSE mount or
exits (measured 15/11 20:37:45: desktop xdg-document-portal failed, status 21,
the second after accept-ptyxis.py's private bus activated portal.Documents).

Here the daemon and every child get a fresh runtime dir under zkey/.tmp.
tests/test_private_bus.py fails if any harness calls dbus-run-session itself.
"""
from pathlib import Path
import atexit
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def private_runtime():
    (ROOT / ".tmp").mkdir(exist_ok=True)
    runtime = Path(tempfile.mkdtemp(prefix="bus-runtime-", dir=ROOT / ".tmp"))
    runtime.chmod(0o700)
    atexit.register(shutil.rmtree, runtime, True)
    return runtime


def command(argv, env, child_real_runtime=False):
    """argv + env for a private bus whose daemon never sees the real runtime dir.

    The daemon, and every service it activates (portals), get a fresh runtime
    dir. child_real_runtime=True hands the real one to the started program only
    (an app that reaches the user's systemd, e.g. ptyxis spawning its shell),
    as when the user starts it; activated services still use the private one.
    """
    env = dict(env)
    real = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env["XDG_RUNTIME_DIR"] = str(private_runtime())
    env.setdefault("ZKEY_REAL_RUNTIME_DIR", real)  # for a caller that must hand it to one app (snap)
    env.pop("WAYLAND_DISPLAY", None)  # relative to the real runtime dir; tests use X11 only
    if child_real_runtime:
        argv = ["env", f"XDG_RUNTIME_DIR={real}", *argv]
    return ["dbus-run-session", "--", *argv], env


def call(argv, env, child_real_runtime=False):
    argv, env = command(argv, env, child_real_runtime)
    return subprocess.call(argv, env=env)


def popen(argv, env, child_real_runtime=False, **kwargs):
    argv, env = command(argv, env, child_real_runtime)
    return subprocess.Popen(argv, env=env, **kwargs)


if __name__ == "__main__":  # shell harnesses: python3 private_bus.py <command...>
    import sys
    raise SystemExit(call(sys.argv[1:], os.environ.copy()))
