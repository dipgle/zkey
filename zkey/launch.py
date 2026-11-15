# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-application entry point; creates a private bus before importing IBus."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile


def main():
    arguments = sys.argv[1:]
    if arguments[:1] != ["--inside"]:
        env = os.environ.copy()
        env.pop("IBUS_USE_PORTAL", None)
        # Preserve the user's zkey preferences before isolating other app state.
        from .config import config_path
        env.setdefault("ZKEY_CONFIG_PATH", str(config_path()))
        env["ZKEY_ISOLATED_BUS"] = "1"
        root = Path(__file__).resolve().parents[1]
        env["PYTHONPATH"] = str(root)
        (root / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="session-", dir=root / ".tmp") as temporary:
            scratch = Path(temporary)
            original_runtime = env.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))
            if display := env.get("WAYLAND_DISPLAY"):
                env["WAYLAND_DISPLAY"] = str(Path(original_runtime) / display)
            for name in ("config", "cache", "data", "runtime"):
                (scratch / name).mkdir(mode=0o700)
            env.update(XDG_CONFIG_HOME=str(scratch / "config"), XDG_CACHE_HOME=str(scratch / "cache"),
                       XDG_DATA_HOME=str(scratch / "data"), XDG_RUNTIME_DIR=str(scratch / "runtime"),
                       GSETTINGS_BACKEND="memory", GIO_USE_VFS="local")
            return subprocess.call(["dbus-run-session", "--", sys.executable, "-m", "zkey.launch", "--inside", *arguments], env=env)
    from .runtime import run_application
    try:
        return run_application(arguments[1:])
    except (OSError, RuntimeError) as error:
        print(f"zkey: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
