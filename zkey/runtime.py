# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run our own IBus daemon for one application, without changing desktop sources."""
from contextlib import contextmanager
from pathlib import Path
import os
import json
import signal
import subprocess
import sys
import tempfile
import time
import shutil

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_engine():
    if os.environ.get("ZKEY_ISOLATED_BUS") != "1":
        raise RuntimeError("This runtime requires a new dbus-run-session")
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=ROOT / ".tmp") as temporary:
        scratch = Path(temporary)
        for name in ("config", "cache", "runtime", "data"):
            (scratch / name).mkdir(mode=0o700)
        env = os.environ.copy()
        env.update(IBUS_ADDRESS=f"unix:path={scratch}/ibus.sock",
                   IBUS_ADDRESS_FILE=str(scratch / "address"),
                   XDG_CONFIG_HOME=str(scratch / "config"), XDG_CACHE_HOME=str(scratch / "cache"),
                   XDG_RUNTIME_DIR=str(scratch / "runtime"), PYTHONPATH=str(ROOT),
                   PYTHONUNBUFFERED="1", GIO_USE_VFS="local", NO_AT_BRIDGE="1",
                   ZKEY_READY_FILE=str(scratch / "ready"))
        # libibus treats presence as true, including the string "0".
        env.pop("IBUS_USE_PORTAL", None)
        os.environ.pop("IBUS_USE_PORTAL", None)
        for key in ("IBUS_ADDRESS", "IBUS_ADDRESS_FILE"):
            os.environ[key] = env[key]
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        # GTK clients use ibus-portal, activated by this private session bus.
        # It must inherit this daemon's address, not the desktop's old address.
        session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        activation = {key: env[key] for key in ("IBUS_ADDRESS", "IBUS_ADDRESS_FILE",
                      "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "GIO_USE_VFS", "NO_AT_BRIDGE")}
        activation.update(XDG_DATA_HOME=str(scratch / "data"), GSETTINGS_BACKEND="memory")
        session_bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                              "UpdateActivationEnvironment", GLib.Variant("(a{ss})", (activation,)),
                              None, Gio.DBusCallFlags.NONE, 5000, None)
        children = []
        log_path = ROOT / ".tmp" / (scratch.name + ".log")
        with log_path.open("w") as log:
            try:
                daemon = subprocess.Popen(["ibus-daemon", "--single", "--panel=disable", "--config=disable",
                    "--emoji-extension=disable", "--cache=none", f"--address={env['IBUS_ADDRESS']}"],
                    env=env, stdout=log, stderr=log, start_new_session=True)
                children.append(daemon)
                deadline = time.monotonic() + 8
                while not (scratch / "ibus.sock").exists():
                    if daemon.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Private IBus could not start; see {log_path}")
                    time.sleep(0.01)
                engine = subprocess.Popen([sys.executable, "-m", "zkey.engine"], cwd=ROOT,
                    env=env, stdout=log, stderr=log, start_new_session=True)
                children.append(engine)
                gi.require_version("IBus", "1.0")
                from gi.repository import IBus
                IBus.init()
                bus = IBus.Bus.new()
                while not (scratch / "ready").exists():
                    if engine.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Engine registration failed; see {log_path}")
                    context = GLib.MainContext.default()
                    while context.pending():
                        context.iteration(False)
                    time.sleep(0.01)
                if not bus.set_global_engine("zkey"):
                    raise RuntimeError(f"Private engine selection failed; see {log_path}")
                client_env = os.environ.copy()
                client_env.update(IBUS_ADDRESS=env["IBUS_ADDRESS"], IBUS_ADDRESS_FILE=env["IBUS_ADDRESS_FILE"],
                                  GTK_IM_MODULE="ibus", QT_IM_MODULE="ibus",
                                  XMODIFIERS="@im=ibus", PYTHONPATH=str(ROOT), GIO_USE_VFS="local",
                                  XDG_CONFIG_HOME=str(scratch / "config"), XDG_CACHE_HOME=str(scratch / "cache"),
                                  XDG_DATA_HOME=str(scratch / "data"), GSETTINGS_BACKEND="memory", NO_AT_BRIDGE="1")
                if backend := os.environ.get("ZKEY_CLIENT_GDK_BACKEND"):
                    client_env["GDK_BACKEND"] = backend
                yield client_env, bus, children
            finally:
                for child in reversed(children):
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()


def run_application(command):
    if not command:
        command = ["gnome-text-editor", "--standalone", "--new-window"]
    with isolated_engine() as (env, _bus, children):
        print("zkey: Telex for this application; system input sources unchanged.", flush=True)
        application = subprocess.Popen(command, env=env)
        try:
            if marker := os.environ.get("ZKEY_APP_PID_FILE"):
                path = Path(marker).resolve()
                if not path.is_relative_to(ROOT / ".tmp"):
                    raise ValueError("Application marker must be within zkey/.tmp")
                path.write_text(json.dumps({"pid": application.pid, "display": env.get("DISPLAY", "")}) + "\n")
            failed = False
            while application.poll() is None:
                if not failed and any(child.poll() is not None for child in children):
                    failed = True
                    message = "zkey đã dừng. Lưu tài liệu trước khi đóng ứng dụng; các phím tiếp theo không còn Telex."
                    print(message, file=sys.stderr, flush=True)
                    if notification := shutil.which("zenity"):
                        subprocess.Popen([notification, "--error", "--title=zkey", "--text=" + message], env=env)
                    else:
                        print("Cannot show failure dialog: zenity unavailable", file=sys.stderr, flush=True)
                time.sleep(0.1)
            return application.returncode or int(failed)
        finally:
            if application.poll() is None:
                application.terminate()
                try:
                    application.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    application.kill()
                    application.wait()
