#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only host session/lock status; never attempts to unlock the desktop."""
import os
import subprocess
import ctypes as C

sessions = subprocess.run(["loginctl", "list-sessions", "--no-legend"], capture_output=True, text=True)
for line in sessions.stdout.splitlines():
    fields = line.split()
    if len(fields) > 1 and fields[1] == str(os.getuid()):
        result = subprocess.run(["loginctl", "show-session", fields[0], "-p", "Active", "-p", "LockedHint", "-p", "State", "-p", "Type"], capture_output=True, text=True)
        print(f"session={fields[0]} status={result.returncode}\n{result.stdout}")
result = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver",
                         "--object-path", "/org/gnome/ScreenSaver", "--method", "org.gnome.ScreenSaver.GetActive"], capture_output=True, text=True)
print(f"screen-saver query={result.returncode}: {result.stdout.strip() or result.stderr.strip()}")
environment = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True)
values = dict(line.split("=", 1) for line in environment.stdout.splitlines() if "=" in line)
if "XAUTHORITY" in values:
    os.environ["XAUTHORITY"] = values["XAUTHORITY"]
if display_name := values.get("DISPLAY"):
    x = C.CDLL("libX11.so.6")
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
    x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
    x.XQueryPointer.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                               C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_uint)]
    x.XCloseDisplay.argtypes = [C.c_void_p]
    display = x.XOpenDisplay(display_name.encode())
    if display:
        root, child, rx, ry, wx, wy, mask = C.c_ulong(), C.c_ulong(), C.c_int(), C.c_int(), C.c_int(), C.c_int(), C.c_uint()
        x.XQueryPointer(display, x.XDefaultRootWindow(display), C.byref(root), C.byref(child),
                        C.byref(rx), C.byref(ry), C.byref(wx), C.byref(wy), C.byref(mask))
        print("modifier-state only:", {name: bool(mask.value & bit) for name, bit in (("Shift", 1), ("Control", 4), ("Alt", 8), ("Super", 64))})
        x.XCloseDisplay(display)
