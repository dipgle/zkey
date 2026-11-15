# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accessibility controls of only the standalone editor launched by this task."""
from pathlib import Path
import os
import gi
import time


def connect(pid):
    values = dict(item.split(b"=", 1) for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0") if b"=" in item)
    address = values[b"DBUS_SESSION_BUS_ADDRESS"].decode()
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    connection = Gio.DBusConnection.new_for_address_sync(address,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
    result = connection.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress", None,
                                  GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, 5000, None)
    os.environ["AT_SPI_BUS_ADDRESS"] = result.unpack()[0]
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    desktop = Atspi.get_desktop(0)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        for index in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(index)
            if app.get_process_id() == pid:
                return Atspi, app
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        time.sleep(0.02)
    raise RuntimeError("Launched editor not exposed through its UI accessibility bus")


def walk(node, depth=0):
    if depth > 45:
        return
    yield node
    for index in range(node.get_child_count()):
        child = node.get_child_at_index(index)
        if child is not None:
            yield from walk(child, depth+1)


def document(pid):
    Atspi, app = connect(pid)
    for node in walk(app):
        states = node.get_state_set()
        if node.get_text_iface() is not None and states.contains(Atspi.StateType.EDITABLE) and states.contains(Atspi.StateType.MULTI_LINE):
            return Atspi, node
    raise RuntimeError("No editable multiline document in the launched editor UI")
