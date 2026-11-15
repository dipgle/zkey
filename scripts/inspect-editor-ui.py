#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only UI exploration of our own standalone test editor, not acceptance."""
from pathlib import Path
import json
import os
import gi

ROOT = Path(__file__).resolve().parents[1]
pid = json.loads((ROOT / ".tmp/editor-app.json").read_text())["pid"]
# Extract only the private bus address; never print the process environment.
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
visited = 0
def inspect(node, depth=0):
    global visited
    visited += 1
    if depth > 45 or visited > 500:
        return
    role, name = node.get_role_name(), node.get_name()
    text = node.get_text_iface()
    content = Atspi.Text.get_text(text, 0, -1) if text else ""
    if name or content or role not in {"panel", "grouping", "filler"}:
        print(f"depth={depth} {role}: {name!r}" + (f" text={content!r}" if content else ""))
    for index in range(node.get_child_count()):
        child = node.get_child_at_index(index)
        if child is not None:
            inspect(child, depth+1)
for index in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(index)
    if app.get_process_id() == pid:
        inspect(app)
