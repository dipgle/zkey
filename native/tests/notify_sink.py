# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test-only notification service: owns org.freedesktop.Notifications on a PRIVATE
session bus and records every Notify call, so a test can prove the warning really
reached a notification service. Never attach it to the user's real session bus."""
from pathlib import Path
import os
import subprocess
import threading

import gi
from gi.repository import Gio, GLib

XML = """<node><interface name='org.freedesktop.Notifications'>
<method name='Notify'><arg type='s' direction='in'/><arg type='u' direction='in'/><arg type='s' direction='in'/>
<arg type='s' direction='in'/><arg type='s' direction='in'/><arg type='as' direction='in'/>
<arg type='a{sv}' direction='in'/><arg type='i' direction='in'/><arg type='u' direction='out'/></method>
</interface></node>"""


class Sink:
    def __init__(self, address):
        self.calls = []
        self._ready = threading.Event()
        self._error = None
        self._loop = None
        self._thread = threading.Thread(target=self._serve, args=(address,), daemon=True)
        self._thread.start()
        if not self._ready.wait(10) or self._error:
            raise RuntimeError(f'Notification sink did not start: {self._error}')

    def _serve(self, address):
        try:
            context = GLib.MainContext.new()
            context.push_thread_default()
            flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
            connection = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
            node = Gio.DBusNodeInfo.new_for_xml(XML)
            connection.register_object('/org/freedesktop/Notifications', node.interfaces[0], self._call, None, None)
            Gio.bus_own_name_on_connection(connection, 'org.freedesktop.Notifications', Gio.BusNameOwnerFlags.NONE,
                                           lambda *_: self._ready.set(), None)
            self._loop = GLib.MainLoop(context)
            self._loop.run()
        except Exception as error:  # reported by the constructor, never swallowed
            self._error = error
            self._ready.set()

    def _call(self, _connection, _sender, _path, _interface, method, parameters, invocation):
        app, _replaces, _icon, summary, body, _actions, hints, timeout = parameters.unpack()
        self.calls.append({'app': app, 'summary': summary, 'body': body,
                           'urgency': hints.get('urgency'), 'timeout': timeout})
        invocation.return_value(GLib.Variant('(u)', (len(self.calls),)))

    def close(self):
        if self._loop is not None:
            self._loop.quit()


class PrivateBus:
    """A private dbus-daemon under project scratch (for tests that have no session bus of their own)."""

    def __init__(self, directory):
        directory = Path(directory)
        self.address = f'unix:path={directory}/bus'
        self.process = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1',
                                         f'--address={self.address}'], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
        if not self.process.stdout.readline().startswith('unix:path='):
            raise RuntimeError('Private dbus-daemon did not print an address')

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)
