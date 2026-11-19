#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""REAL Firefox (official tarball, ZKEY_FIREFOX) + REAL XTest keys + the NATIVE engine.

Same assertions as scripts/accept-firefox.py (per-key prefixes read from the page's own
value, 'tiếng việt', Backspace, password unchanged, 0 composition events). Only the
engine differs: the private ibus-daemon starts `zkey-native --ibus --experimental-rewrite`
from a component XML itself (the production path), instead of the legacy Python engine.
Private Xvfb (ZKEY_TEST_DISPLAY), private D-Bus (scripts/private_bus.py), throwaway
profile under zkey/.tmp. Exit 0 pass, 1 fail, 2 not measurable; ends GATE_EXIT.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import contextlib
import importlib.util
import re  # noqa: F401  (used by the xev watcher)
import os
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import private_bus  # noqa: E402  (never dbus-run-session directly)

spec = importlib.util.spec_from_file_location("accept_firefox_base", ROOT / "scripts/accept-firefox.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

BINARY = ROOT / "native/target/release/zkey-native"

# The page is a local file: NOTHING in this browser may reach the network. Every HTTP/HTTPS/FTP/SOCKS
# request goes to a dead local port, and updates, telemetry, safe browsing, captive-portal checks,
# DNS prefetch and DoH are off. (The test never needs the internet.)
OFFLINE_PREFS = """user_pref("network.proxy.type", 1);
user_pref("network.proxy.http", "127.0.0.1");
user_pref("network.proxy.http_port", 9);
user_pref("network.proxy.ssl", "127.0.0.1");
user_pref("network.proxy.ssl_port", 9);
user_pref("network.proxy.ftp", "127.0.0.1");
user_pref("network.proxy.ftp_port", 9);
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", 9);
user_pref("network.proxy.no_proxies_on", "");
user_pref("app.update.enabled", false);
user_pref("app.update.service.enabled", false);
user_pref("extensions.update.enabled", false);
user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
user_pref("browser.safebrowsing.downloads.enabled", false);
user_pref("network.captive-portal-service.enabled", false);
user_pref("network.connectivity-service.enabled", false);
user_pref("network.dns.disablePrefetch", true);
user_pref("network.prefetch-next", false);
user_pref("network.predictor.enabled", false);
user_pref("network.trr.mode", 5);
user_pref("toolkit.telemetry.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("browser.region.update.enabled", false);
user_pref("media.gmp-manager.url", "");
"""
base.PREFS = base.PREFS + OFFLINE_PREFS

COMPONENT = """<?xml version="1.0" encoding="utf-8"?>
<component>
  <name>org.freedesktop.IBus.ZkeyNative</name>
  <description>zkey native</description>
  <version>0.2.0-dev</version>
  <license>AGPL-3.0-or-later</license>
  <author>zkey contributors</author>
  <exec>{exec}</exec>
  <textdomain>zkey-native</textdomain>
  <engines>
    <engine>
      <name>zkey-native</name>
      <longname>zkey native</longname>
      <description>Vietnamese Telex</description>
      <language>vi</language>
      <license>AGPL-3.0-or-later</license>
      <author>zkey contributors</author>
      <icon>input-keyboard</icon>
      <layout>us</layout>
    </engine>
  </engines>
</component>
"""


@contextlib.contextmanager
def native_engine():
    """Drop-in for zkey.runtime.isolated_engine: yields (client_env, bus, children)."""
    from zkey.runtime import session_runtime
    if os.environ.get("ZKEY_ISOLATED_BUS") != "1":
        raise RuntimeError("This runtime requires a private bus (scripts/private_bus.py)")
    bus_runtime = session_runtime(os.environ)
    with tempfile.TemporaryDirectory(prefix="run-", dir=ROOT / ".tmp") as temporary:
        scratch = Path(temporary)
        for name in ("config", "cache", "runtime", "data", "component"):
            (scratch / name).mkdir(mode=0o700)
        log_path = ROOT / ".tmp" / (scratch.name + ".log")
        # ibus-daemon discards a child's stderr, so the engine trace goes to the log through
        # sh; "key-event" is also written as "key-state" so the base assertion that counts
        # keys the engine saw measures THIS engine (same meaning, native wording).
        command = (f'/bin/sh -c "exec {BINARY} --ibus --experimental-rewrite 2>&1 | '
                   f"sed -u 's/zkey-native: key-event/zkey-native: key-state key-event/' >> {log_path}\"")
        (scratch / "component/zkey-native.xml").write_text(COMPONENT.format(exec=escape(command)))
        env = os.environ.copy()
        env.update(IBUS_ADDRESS=f"unix:path={scratch}/ibus.sock", IBUS_ADDRESS_FILE=str(scratch / "address"),
                   XDG_CONFIG_HOME=str(scratch / "config"), XDG_CACHE_HOME=str(scratch / "cache"),
                   XDG_RUNTIME_DIR=str(bus_runtime), GIO_USE_VFS="local", NO_AT_BRIDGE="1",
                   ZKEY_NATIVE_CONFIG_PATH=str(scratch / "preferences.toml"), ZKEY_NATIVE_TRACE="1",
                   IBUS_COMPONENT_PATH=f"/usr/share/ibus/component:{scratch}/component")
        env.pop("IBUS_USE_PORTAL", None)
        os.environ.pop("IBUS_USE_PORTAL", None)
        for key in ("IBUS_ADDRESS", "IBUS_ADDRESS_FILE"):
            os.environ[key] = env[key]
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)  # the PRIVATE bus (checked by session_runtime)
        activation = {key: env[key] for key in ("IBUS_ADDRESS", "IBUS_ADDRESS_FILE", "XDG_CONFIG_HOME",
                      "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "GIO_USE_VFS", "NO_AT_BRIDGE")}
        activation.update(XDG_DATA_HOME=str(scratch / "data"), GSETTINGS_BACKEND="memory")
        session_bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                              "UpdateActivationEnvironment", GLib.Variant("(a{ss})", (activation,)),
                              None, Gio.DBusCallFlags.NONE, 5000, None)
        children = []
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
                gi.require_version("IBus", "1.0")
                from gi.repository import IBus
                IBus.init()
                bus = IBus.Bus.new()
                if not bus.set_global_engine("zkey-native"):
                    raise RuntimeError(f"Native engine selection failed; see {log_path}")
                client_env = os.environ.copy()
                client_env.update(IBUS_ADDRESS=env["IBUS_ADDRESS"], IBUS_ADDRESS_FILE=env["IBUS_ADDRESS_FILE"],
                                  GTK_IM_MODULE="ibus", QT_IM_MODULE="ibus", XMODIFIERS="@im=ibus",
                                  GIO_USE_VFS="local", XDG_CONFIG_HOME=str(scratch / "config"),
                                  XDG_CACHE_HOME=str(scratch / "cache"), XDG_DATA_HOME=str(scratch / "data"),
                                  GSETTINGS_BACKEND="memory", NO_AT_BRIDGE="1", XDG_RUNTIME_DIR=str(bus_runtime),
                                  IBUS_ENABLE_SYNC_MODE="1")
                if module := os.environ.get("ZKEY_CLIENT_IM_MODULE"):
                    # Control only: same Firefox and keys WITHOUT the engine in the client's input path.
                    client_env["GTK_IM_MODULE"] = module
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


def instrument():
    """Test-harness diagnostics/variants (never product behaviour)."""
    import threading
    original = base.x11

    def patched():
        x, t = original()
        if os.environ.get("ZKEY_FF_NO_FOCUS") == "1":
            # Variant: never force X input focus; keys follow the pointer (PointerRoot) like a real
            # user whose click put the pointer over the page.
            x.XSetInputFocus = lambda *args: 0
        return x, t
    base.x11 = patched
    if os.environ.get("ZKEY_FF_GFX") == "1":
        # Variant for a GPU-less Xvfb: measured 19/11 "VideoBridgeParent … AbnormalShutdown" and a
        # sandbox EPERM; force software rendering and drop the child-process sandboxes (test only).
        base.PREFS += """user_pref("gfx.webrender.software", true);
user_pref("layers.acceleration.disabled", true);
user_pref("gfx.canvas.accelerated", false);
user_pref("media.rdd-process.enabled", false);
user_pref("media.utility-process.enabled", false);
user_pref("security.sandbox.content.level", 0);
user_pref("browser.tabs.remote.autostart", true);
"""
        for name in ("MOZ_DISABLE_CONTENT_SANDBOX", "MOZ_DISABLE_RDD_SANDBOX", "MOZ_DISABLE_GMP_SANDBOX",
                     "MOZ_DISABLE_SOCKET_PROCESS_SANDBOX", "MOZ_DISABLE_GPU_SANDBOX"):
            os.environ[name] = "1"
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"

    if os.environ.get("ZKEY_FF_TESTMODE") == "1":
        # Measured 19/11 with xev: the key REACHES Firefox's content window (KeyPress, synthetic NO)
        # yet the page sees keys=0. No window manager here, so Firefox never counts its window as
        # activated. focusmanager.testmode makes Gecko ignore OS-level window activation (the pref
        # Mozilla's own test suites use). Test environment only.
        base.PREFS += 'user_pref("focusmanager.testmode", true);\n'

    def dump(tag):
        with (ROOT / f".tmp/firefox-xtree-{tag}.txt").open("w") as out:
            subprocess.run(["xwininfo", "-root", "-tree"], stdout=out, stderr=subprocess.STDOUT, timeout=20)
    def watch_x_events():
        """Attach xev to Firefox's content window: do key/pointer events reach the X window at all?"""
        import re
        deadline = time.monotonic() + 165
        while time.monotonic() < deadline:
            tree = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, timeout=20).stdout
            found = re.search(r'(0x[0-9a-f]+) "[^"\n]*": \("Navigator" "firefox"\)[^\n]*\n\s+\d+ children?:\n\s+(0x[0-9a-f]+)', tree)
            if found:
                with (ROOT / ".tmp/firefox-xev.txt").open("w") as out:
                    out.write(f"toplevel={found.group(1)} content={found.group(2)}\n")
                    out.flush()
                    process = subprocess.Popen(["xev", "-id", found.group(2), "-event", "keyboard", "-event", "mouse"],
                                               stdout=out, stderr=subprocess.STDOUT)
                    try:
                        process.wait(timeout=max(1, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        process.terminate()
                return
            time.sleep(1)
    threading.Thread(target=watch_x_events, daemon=True).start()
    for seconds in (10, 25, 45):
        timer = threading.Timer(seconds, dump, args=(f"{seconds}s",))
        timer.daemon = True
        timer.start()


def main():
    if sys.argv[1:] == ["--inside"]:
        import zkey.runtime
        zkey.runtime.isolated_engine = native_engine  # base.inside() imports it at call time
        instrument()
        try:
            return base.inside()
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
    if not BINARY.is_file() or not os.environ.get("ZKEY_FIREFOX"):
        print("NOT_MEASURABLE: need native/target/release/zkey-native and ZKEY_FIREFOX=<non-snap firefox>")
        return 2
    env = os.environ.copy()
    env["DISPLAY"] = display
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("IBUS_USE_PORTAL", None)
    env.update(ZKEY_ISOLATED_BUS="1", GTK_IM_MODULE="ibus", GDK_BACKEND="x11", NO_AT_BRIDGE="1", GIO_USE_VFS="local")
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), "--inside"], env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
