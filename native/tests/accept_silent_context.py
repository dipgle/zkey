#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A context that resets after every commit and never republishes its text.

Measured 20/11 (Files search entry, engine trace lines 2939-2973): the context
publishes ONE empty snapshot when it is created, then calls Reset after every
commit and never sends SetSurroundingText again, so the engine can never prove
the word is still in the field. The engine must keep its own buffer there;
without it every key was a plain insert (remove=0 insert_chars=1) and
`tieengs`/`mowis` never became `tiếng`/`mới`.

Reverse control in the SAME run: a fresh engine whose client never publishes a
snapshot at all must stay raw (no deletes). A buffer that guesses in that case
turns this gate RED, so the gate can fail in both directions.

Exit 0 both directions hold, 1 red, 2 not measurable. Synthetic keys only.
"""
from pathlib import Path
import glob
import os
import re
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

CASES = [("tieengs", "tiếng"), ("mowis", "mới"), ("ddaua", "đâu")]
COMPONENT = "org.freedesktop.IBus.ZkeyNative"
FACTORY_PATH = "/org/freedesktop/IBus/Factory"
FACTORY = "org.freedesktop.IBus.Factory"
ENGINE = "org.freedesktop.IBus.Engine"
PROPERTIES = "org.freedesktop.DBus.Properties"


def not_measurable(reason):
    print(f"NOT_MEASURABLE: {reason}")
    print("GATE_EXIT=2")
    return 2


def daemon_address():
    """The running ibus-daemon's private bus: env first, else its address file."""
    env = os.environ.get("IBUS_ADDRESS")
    if env:
        return env
    best = None
    for name in glob.glob(str(Path.home() / ".config/ibus/bus/*")):
        try:
            text = Path(name).read_text(errors="replace")
        except OSError:
            continue
        address = re.search(r"^IBUS_ADDRESS=(\S+)$", text, re.M)
        pid = re.search(r"^IBUS_DAEMON_PID=(\d+)$", text, re.M)
        if not address or not pid or not Path(f"/proc/{pid.group(1)}").exists():
            continue
        socket = address.group(1).removeprefix("unix:path=").split(",")[0].split("guid=")[0]
        if not Path(socket).exists():
            continue
        mtime = Path(name).stat().st_mtime
        if best is None or mtime > best[0]:
            best = (mtime, address.group(1))
    return best[1] if best else None


class Client:
    def __init__(self, connection):
        self.connection = connection
        self.text = ""
        self.cursor = 0
        self.removes = 0
        self.commits = 0
        self.signals = []

    def subscribe(self, path):
        def on_signal(_conn, _sender, _path, _iface, name, params, _user):
            self.signals.append((name, params))

        self.subscription = self.connection.signal_subscribe(
            COMPONENT, ENGINE, None, path, None, Gio.DBusSignalFlags.NONE, on_signal, None
        )

    def pump(self, seconds=0.05):
        context = GLib.MainContext.default()
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            while context.pending():
                context.iteration(False)
            time.sleep(0.002)
        while context.pending():
            context.iteration(False)

    def apply_signals(self):
        self.pump()
        for name, params in self.signals:
            values = params.unpack()
            if name == "DeleteSurroundingText":
                count = int(values[1])
                if count > self.cursor:
                    raise AssertionError(f"engine deleted {count} chars with cursor {self.cursor}")
                self.text = self.text[: self.cursor - count] + self.text[self.cursor :]
                self.cursor -= count
                self.removes += 1
            elif name == "CommitText":
                inner = values[0]
                insert = inner[2]
                if not isinstance(insert, str):
                    raise AssertionError("CommitText payload is not a string")
                self.text = self.text[: self.cursor] + insert + self.text[self.cursor :]
                self.cursor += len(insert)
                self.commits += 1
        self.signals.clear()

    def call(self, path, interface, method, params, reply=None):
        return self.connection.call_sync(
            COMPONENT, path, interface, method, params, reply, 0, 5000, None
        )

    def publish(self, path):
        """The one and only snapshot this context ever sends."""
        attrs = GLib.Variant("(sa{sv}av)", ("IBusAttrList", {}, []))
        text = GLib.Variant("(sa{sv}sv)", ("IBusText", {}, self.text, attrs))
        self.call(path, ENGINE, "SetSurroundingText",
                  GLib.Variant("(vuu)", (text, len(self.text), len(self.text))))
        self.apply_signals()

    def key(self, path, char):
        """Edit -> (client applies) -> Reset. Never publishes text again."""
        handled = self.call(
            path, ENGINE, "ProcessKeyEvent",
            GLib.Variant("(uuu)", (ord(char), 0, 0)), GLib.VariantType("(b)")
        ).unpack()[0]
        self.apply_signals()
        self.call(path, ENGINE, "Reset", None)
        self.apply_signals()
        return handled


def run_case(connection, keys, publish_first):
    engine = connection.call_sync(
        COMPONENT, FACTORY_PATH, FACTORY, "CreateEngine",
        GLib.Variant("(s)", ("zkey-native",)), GLib.VariantType("(o)"), 0, 5000, None,
    ).unpack()[0]
    client = Client(connection)
    client.subscribe(engine)
    try:
        client.call(engine, ENGINE, "SetCapabilities", GLib.Variant("(u)", (41,)))
        client.call(engine, PROPERTIES, "Set",
                    GLib.Variant("(ssv)", (ENGINE, "ContentType", GLib.Variant("(uu)", (0, 0)))))
        if publish_first:
            client.publish(engine)
        for char in keys:
            if not client.key(engine, char):
                print(f"FAIL: engine did not handle {char!r}; text={client.text!r}")
                return None
    finally:
        client.connection.signal_unsubscribe(client.subscription)
        try:
            client.call(engine, ENGINE, "Destroy", None)
        except GLib.Error:
            pass
    return client


def main():
    address = daemon_address()
    if not address:
        return not_measurable("no running ibus-daemon address")
    if not (Path.home() / ".local/lib/zkey-native/zkey-native").is_file():
        return not_measurable("native engine is not installed (scripts/native-ime.py enable)")
    try:
        connection = Gio.DBusConnection.new_for_address_sync(
            address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None,
            None,
        )
    except GLib.Error as error:
        return not_measurable(f"cannot connect to the ibus bus: {error.message}")

    failures = 0
    for keys, expected in CASES:
        client = run_case(connection, keys, publish_first=True)
        if client is None:
            return 2
        print(f"RESULT silent keys={keys!r} text={client.text!r} expected={expected!r} "
              f"removes={client.removes} commits={client.commits}")
        if client.text != expected or client.removes == 0:
            print(f"FAIL silent-context: engine lost composition without snapshots ({keys})")
            failures += 1

    # Reverse control: the client never published the field, so the engine must
    # not guess — every key stays a literal insert.
    client = run_case(connection, "tieengs", publish_first=False)
    if client is None:
        return 2
    print(f"RESULT unpublished keys='tieengs' text={client.text!r} removes={client.removes}")
    if client.text != "tieengs" or client.removes != 0:
        print("FAIL silent-control: engine deleted text it was never shown")
        failures += 1

    print(f"GATE_EXIT={1 if failures else 0}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
