#!/usr/bin/python3
"""EXPLORATORY protocol probe, not UI acceptance. Never connects to the user's bus.

Run under dbus-run-session. All XDG state and sockets live under zkey/.tmp.
Direct InputContext calls are intentional protocol checks; compensate with a
separate, still-required real desktop typing matrix before acceptance.
"""
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import time
import warnings

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.environ.pop("IBUS_USE_PORTAL", None)
    if not os.environ.get("ZKEY_ISOLATED_BUS"):
        print("NOT_MEASURABLE: use dbus-run-session with ZKEY_ISOLATED_BUS=1", flush=True)
        return 2
    import gi
    gi.require_version("IBus", "1.0")
    from gi.repository import GLib, IBus
    # Fail on the ownership warning under investigation; system GI also imports
    # deprecated asyncio compatibility code unrelated to this protocol.
    warnings.filterwarnings("error", message=".*g_object_is_floating.*")
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ibus-", dir=ROOT / ".tmp") as scratch:
        scratch = Path(scratch)
        for name in ("config", "cache", "runtime"):
            (scratch / name).mkdir(mode=0o700)
        env = os.environ.copy()
        env.update(XDG_CONFIG_HOME=str(scratch / "config"), XDG_CACHE_HOME=str(scratch / "cache"),
                   XDG_RUNTIME_DIR=str(scratch / "runtime"), IBUS_ADDRESS=f"unix:path={scratch}/ibus.sock",
                   IBUS_ADDRESS_FILE=str(scratch / "address"), PYTHONPATH=str(ROOT),
                   PYTHONUNBUFFERED="1", GIO_USE_VFS="local", ZKEY_TRACE="1",
                   ZKEY_READY_FILE=str(scratch / "ready"))
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        os.environ.update({key: env[key] for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "IBUS_ADDRESS", "IBUS_ADDRESS_FILE")})
        processes = []
        log = (scratch / "probe.log").open("w+")
        try:
            daemon = subprocess.Popen(["ibus-daemon", "--single", "--panel=disable", "--config=disable",
                "--emoji-extension=disable", "--cache=none", f"--address={env['IBUS_ADDRESS']}"],
                env=env, stdout=log, stderr=log, start_new_session=True)
            processes.append(daemon)
            deadline = time.monotonic() + 5
            while not (scratch / "ibus.sock").exists():
                if daemon.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Isolated IBus daemon did not create socket")
                time.sleep(0.01)
            engine = subprocess.Popen([sys.executable, "-m", "zkey.engine"], cwd=ROOT,
                                      env=env, stdout=log, stderr=log, start_new_session=True)
            processes.append(engine)
            IBus.init()
            bus = IBus.Bus.new()
            if not bus.is_connected():
                raise RuntimeError("Cannot connect to isolated IBus")
            context = bus.create_input_context("zkey-protocol-probe")
            context.set_capabilities(int(IBus.Capabilite.SURROUNDING_TEXT | IBus.Capabilite.PREEDIT_TEXT | IBus.Capabilite.FOCUS))
            commits, preedits, errors = [], [], []
            received_texts = []
            document = {"text": "", "cursor": 0}

            def update():
                context.set_surrounding_text(IBus.Text.new_from_string(document["text"]),
                                             document["cursor"], document["cursor"])

            def commit(_context, text):
                # libibus inspects its floating Text after signal emission.
                # Keep the GI wrapper alive until this finite probe finishes.
                received_texts.append(text)
                value = text.get_text()
                commits.append(value)
                cursor = document["cursor"]
                document["text"] = document["text"][:cursor] + value + document["text"][cursor:]
                document["cursor"] += len(value)
                update()

            def delete(_context, offset, count):
                start = document["cursor"] + offset
                if not 0 <= start <= start + count <= len(document["text"]):
                    errors.append("Delete outside confirmed text")
                    return
                document["text"] = document["text"][:start] + document["text"][start+count:]
                document["cursor"] = start
                update()

            context.connect("commit-text", commit)
            context.connect("delete-surrounding-text", delete)
            context.connect("require-surrounding-text", lambda *_args: update())
            def preedit(_context, text, *_args):
                received_texts.append(text)
                preedits.append(text.get_text())
            context.connect("update-preedit-text", preedit)

            def pump_until(predicate, message):
                deadline = time.monotonic() + 5
                main_context = GLib.MainContext.default()
                while not predicate():
                    while main_context.pending():
                        main_context.iteration(False)
                    if errors:
                        raise RuntimeError(errors[0])
                    if engine.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(message)
                    time.sleep(0.005)

            # Engine selection is confined to this new daemon and new session bus.
            def selected():
                if not (scratch / "ready").exists():
                    return False
                bus.set_global_engine("zkey")
                context.set_engine("zkey")
                description = context.get_engine()
                return description is not None and description.get_name() == "zkey"

            context.focus_in()
            pump_until(selected, "Engine not registered or selected")
            context.set_content_type(IBus.InputPurpose.FREE_FORM, 0)
            update()
            for key, expected in zip("tieengs", ("t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng")):
                assert context.process_key_event(ord(key), 0, 0), "Alphabetic key unexpectedly passed through"
                pump_until(lambda: document["text"] == expected, "App did not receive per-key edit")
            assert not context.process_key_event(IBus.KEY_space, 0, 0), "Delimiter should pass through"
            assert document["text"] == "tiếng", "Duplicate boundary commit"
            for purpose in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN, IBus.InputPurpose.TERMINAL):
                context.set_content_type(purpose, 0)
                for key in "as":
                    assert not context.process_key_event(ord(key), 0, 0), "Protected key consumed"
            context.set_content_type(IBus.InputPurpose.FREE_FORM, 0)
            document.update(text="", cursor=0)
            update()
            for key in "ans":
                assert context.process_key_event(ord(key), 0, 0)
                pump_until(lambda: document["text"] == {"a": "a", "n": "an", "s": "án"}[key], "Wrong per-key text")
            assert not context.process_key_event(IBus.KEY_BackSpace, 0, 0), "Backspace must remain native"
            document.update(text="á", cursor=1)
            update()
            assert context.process_key_event(ord("n"), 0, 0)
            pump_until(lambda: document["text"] == "án", "Backspace continuation regression")
            assert not any(preedits), "Visible preedit in direct mode"
            context.focus_out()
            context.destroy()
            print("PASS protocol: per-key commit, confirmed surrounding edits, native boundary, PASSWORD/PIN/TERMINAL bypass, backspace (7 groups).")
            print("Not UI acceptance or keyboard-to-screen latency.")
            return 0
        except (OSError, RuntimeError, AssertionError) as error:
            print(f"PROBE FAILED: {error}", file=sys.stderr)
            log.flush()
            log.seek(0)
            print(log.read(), file=sys.stderr)
            return 1
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            log.close()


if __name__ == "__main__":
    code = main()
    print(f"GATE_EXIT={code}", flush=True)
    raise SystemExit(code)
