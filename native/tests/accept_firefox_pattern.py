#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Firefox call pattern against the INSTALLED native engine, over the real IBus bus.

Firefox's GTK IM context (measured 19/11 in the user's trace) calls the engine like
this on every key:  edit -> Reset -> SetSurroundingText.  The old engine dropped its
word on that Reset, so every key became a plain insert (remove=0 insert_chars=1) and
`tieengs` never became `tiếng`.

This checks the running, installed engine directly (no GUI, no key injection, no
input-source change): create one engine context through the public factory, feed the
same call sequence, apply the edits, and assert the resulting text.

Exit 0 pass, 1 red, 2 not measurable (engine not installed/running). Only metadata
and the one synthetic word are handled; nothing is written to the user's document.
"""
from pathlib import Path
import glob
import os
import re
import sys
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

WORD = "tieengs"
EXPECTED = "tiếng"
# Reverse control: a client that resets and never republishes its text must come
# out raw. Turns this gate RED if the assertion stops noticing lost composition.
SKIP_SURROUNDING = os.environ.get("ZKEY_FIREFOX_SKIP_SURROUNDING") == "1"
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
        self.handled = 0
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
                # (v) wrapping IBus.Text (sa{sv}sv): the text is the third field.
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

    def surrounding(self, path):
        attrs = GLib.Variant("(sa{sv}av)", ("IBusAttrList", {}, []))
        text = GLib.Variant("(sa{sv}sv)", ("IBusText", {}, self.text, attrs))
        self.call(path, ENGINE, "SetSurroundingText",
                  GLib.Variant("(vuu)", (text, len(self.text), len(self.text))))
        self.apply_signals()

    def key(self, path, char):
        handled = self.call(
            path, ENGINE, "ProcessKeyEvent",
            GLib.Variant("(uuu)", (ord(char), 0, 0)), GLib.VariantType("(b)")
        ).unpack()[0]
        self.apply_signals()
        self.call(path, ENGINE, "Reset", None)
        self.apply_signals()
        if not SKIP_SURROUNDING:
            self.surrounding(path)
        return handled


def main():
    address = daemon_address()
    if not address:
        return not_measurable("no running ibus-daemon address")
    installed = Path.home() / ".local/lib/zkey-native/zkey-native"
    if not installed.is_file():
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
    try:
        engine = connection.call_sync(
            COMPONENT, FACTORY_PATH, FACTORY, "CreateEngine",
            GLib.Variant("(s)", ("zkey-native",)), GLib.VariantType("(o)"), 0, 5000, None,
        ).unpack()[0]
    except GLib.Error as error:
        return not_measurable(f"installed engine does not serve CreateEngine: {error.message}")

    client = Client(connection)
    client.subscribe(engine)
    try:
        # Same capabilities Firefox advertises (32 = surrounding text, plus preedit bits).
        client.call(engine, ENGINE, "SetCapabilities", GLib.Variant("(u)", (41,)))
        content = GLib.Variant("(uu)", (0, 0))
        client.call(engine, PROPERTIES, "Set",
                    GLib.Variant("(ssv)", (ENGINE, "ContentType", content)))
        client.surrounding(engine)
        for char in WORD:
            if not client.key(engine, char):
                print(f"FAIL: engine did not handle {char!r}; text={client.text!r}")
                return 1
            client.handled += 1
    finally:
        client.connection.signal_unsubscribe(client.subscription)
        try:
            client.call(engine, ENGINE, "Destroy", None)
        except GLib.Error:
            pass

    print(f"RESULT text={client.text!r} expected={EXPECTED!r} "
          f"keys={client.handled} removes={client.removes} commits={client.commits}")
    if client.text == EXPECTED and client.removes > 0:
        print("PASS firefox-pattern: installed engine composes across Reset after every commit")
        print("GATE_EXIT=0")
        return 0
    print("FAIL firefox-pattern: engine lost composition across client Reset")
    print("GATE_EXIT=1")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
