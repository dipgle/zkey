# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ask the window manager to activate a test window, and verify its decision."""
import ctypes as C
import time


class Data(C.Union):
    _fields_ = [("bytes", C.c_char * 20), ("shorts", C.c_short * 10), ("longs", C.c_long * 5)]


class Message(C.Structure):
    _fields_ = [("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
                ("display", C.c_void_p), ("window", C.c_ulong), ("message_type", C.c_ulong),
                ("format", C.c_int), ("data", Data)]


class Event(C.Union):
    _fields_ = [("message", Message), ("padding", C.c_long * 24)]


def active_window(x, display):
    x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
    x.XInternAtom.argtypes, x.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
    x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
                                    C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                    C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ubyte))]
    x.XFree.argtypes = [C.c_void_p]
    actual, fmt, count, rest = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
    data = C.POINTER(C.c_ubyte)()
    root = x.XDefaultRootWindow(display)
    atom = x.XInternAtom(display, b"_NET_ACTIVE_WINDOW", False)
    code = x.XGetWindowProperty(display, root, atom, 0, 1, False, 0, C.byref(actual), C.byref(fmt),
                                C.byref(count), C.byref(rest), C.byref(data))
    try:
        if code or fmt.value != 32 or count.value != 1 or not data:
            return None
        return C.cast(data, C.POINTER(C.c_ulong))[0]
    finally:
        if data:
            x.XFree(data)


class PropertyEvent(C.Structure):
    _fields_ = [("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
                ("display", C.c_void_p), ("window", C.c_ulong), ("atom", C.c_ulong),
                ("time", C.c_ulong), ("state", C.c_int)]


class AnyEvent(C.Union):
    _fields_ = [("type", C.c_int), ("property", PropertyEvent), ("padding", C.c_long * 24)]


def server_time(x, display):
    """Current X server time, from a PropertyNotify on a private unmapped window.

    Mutter refuses _NET_ACTIVE_WINDOW with timestamp 0 once another window has
    newer user input (measured 15/11: target never activated). A real server
    timestamp is the EWMH way for a window controller to prove recency.
    """
    x.XCreateSimpleWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint,
                                      C.c_uint, C.c_ulong, C.c_ulong]
    x.XCreateSimpleWindow.restype = C.c_ulong
    x.XSelectInput.argtypes = [C.c_void_p, C.c_ulong, C.c_long]
    x.XChangeProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_ulong, C.c_int, C.c_int,
                                  C.c_char_p, C.c_int]
    x.XWindowEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_long, C.POINTER(AnyEvent)]
    x.XDestroyWindow.argtypes = [C.c_void_p, C.c_ulong]
    probe = x.XCreateSimpleWindow(display, x.XDefaultRootWindow(display), -10, -10, 1, 1, 0, 0, 0)
    if not probe:
        raise RuntimeError("Cannot create timestamp probe window")
    try:
        property_change_mask = 1 << 22
        x.XSelectInput(display, probe, property_change_mask)
        atom = x.XInternAtom(display, b"ZKEY_TIMESTAMP", False)
        x.XChangeProperty(display, probe, atom, atom, 8, 2, b"", 0)  # PropModeAppend, zero length.
        event = AnyEvent()
        x.XWindowEvent(display, probe, property_change_mask, C.byref(event))
        if event.type != 28 or not event.property.time:  # PropertyNotify
            raise RuntimeError("X server returned no timestamp")
        return event.property.time
    finally:
        x.XDestroyWindow(display, probe)
        x.XFlush(display)


def free_position(x, display, width, height, margin=60):
    """Top-left of a workarea spot not overlapping any managed X11 client.

    A window refused focus is stacked under the focused one; a click meant for
    it would land on the other window. Wayland-native windows are invisible
    here, so callers must still verify activation before typing.
    """
    x.XGetGeometry.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int),
                               C.POINTER(C.c_int), C.POINTER(C.c_uint), C.POINTER(C.c_uint),
                               C.POINTER(C.c_uint), C.POINTER(C.c_uint)]
    x.XTranslateCoordinates.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_int, C.c_int,
                                        C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_ulong)]
    root = x.XDefaultRootWindow(display)

    def values(window, name):
        actual, fmt, count, rest = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
        data = C.POINTER(C.c_ubyte)()
        code = x.XGetWindowProperty(display, window, x.XInternAtom(display, name, False), 0, 4096, False, 0,
                                    C.byref(actual), C.byref(fmt), C.byref(count), C.byref(rest), C.byref(data))
        try:
            return list(C.cast(data, C.POINTER(C.c_ulong))[:count.value]) if not code and data and fmt.value == 32 else []
        finally:
            if data:
                x.XFree(data)

    occupied = []
    for client in values(root, b"_NET_CLIENT_LIST_STACKING"):
        parent, gx, gy, w, h, border, depth = C.c_ulong(), C.c_int(), C.c_int(), C.c_uint(), C.c_uint(), C.c_uint(), C.c_uint()
        if not x.XGetGeometry(display, client, C.byref(parent), C.byref(gx), C.byref(gy), C.byref(w), C.byref(h),
                              C.byref(border), C.byref(depth)):
            continue
        ox, oy, child = C.c_int(), C.c_int(), C.c_ulong()
        x.XTranslateCoordinates(display, client, root, 0, 0, C.byref(ox), C.byref(oy), C.byref(child))
        occupied.append((ox.value, oy.value, ox.value + w.value, oy.value + h.value))
    area = values(root, b"_NET_WORKAREA")[:4] or [0, 0, 1024, 768]
    left, top, right, bottom = area[0], area[1], area[0] + area[2], area[1] + area[3]
    need_w, need_h = width + 2 * margin, height + 2 * margin
    for y in range(top, bottom - need_h + 1, 40):
        for x0 in range(left, right - need_w + 1, 40):
            box = (x0, y, x0 + need_w, y + need_h)
            if all(box[2] <= o[0] or o[2] <= box[0] or box[3] <= o[1] or o[3] <= box[1] for o in occupied):
                return x0 + margin, y + margin
    return None


def has_window_manager(x, display):
    """EWMH manager present? A private Xvfb test display has none."""
    x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
    x.XInternAtom.argtypes, x.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
    x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
                                    C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                    C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ubyte))]
    x.XFree.argtypes = [C.c_void_p]
    actual, fmt, count, rest = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
    data = C.POINTER(C.c_ubyte)()
    code = x.XGetWindowProperty(display, x.XDefaultRootWindow(display),
                                x.XInternAtom(display, b"_NET_SUPPORTING_WM_CHECK", False), 0, 1, False, 0,
                                C.byref(actual), C.byref(fmt), C.byref(count), C.byref(rest), C.byref(data))
    try:
        return not code and bool(data) and count.value == 1
    finally:
        if data:
            x.XFree(data)


def focused_within(x, display, window):
    """X keyboard focus is window or one of its descendants."""
    x.XGetInputFocus.argtypes = [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]
    x.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                             C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
    focus, revert = C.c_ulong(), C.c_int()
    x.XGetInputFocus(display, C.byref(focus), C.byref(revert))
    candidate = focus.value
    for _level in range(16):
        if candidate == window:
            return True
        if candidate <= 1:  # None / PointerRoot
            return False
        root, parent, children, count = C.c_ulong(), C.c_ulong(), C.POINTER(C.c_ulong)(), C.c_uint()
        result = x.XQueryTree(display, candidate, C.byref(root), C.byref(parent), C.byref(children), C.byref(count))
        if children:
            x.XFree(children)
        if not result or not parent.value or parent.value == candidate:
            return False
        candidate = parent.value
    return False


def is_active(x, display, window):
    """With a window manager, its decision; without one, the X focus itself."""
    if has_window_manager(x, display):
        return active_window(x, display) == window
    return focused_within(x, display, window)


def activate(x, display, window, pump=lambda: time.sleep(0.02)):
    if not has_window_manager(x, display):
        x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        x.XSync.argtypes = [C.c_void_p, C.c_int]
        x.XSetInputFocus(display, window, 2, 0)  # RevertToParent, CurrentTime
        x.XSync(display, False)
        until = time.monotonic() + 3
        while time.monotonic() < until:
            if focused_within(x, display, window):
                return
            pump()
        raise RuntimeError(f"Test display did not focus window {window}")
    previous = active_window(x, display)
    x.XSendEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(Event)]
    event = Event()
    event.message.type, event.message.display = 33, display
    event.message.window = window
    event.message.message_type = x.XInternAtom(display, b"_NET_ACTIVE_WINDOW", False)
    event.message.format = 32
    event.message.data.longs[0] = 2  # Standard EWMH request from a window controller.
    event.message.data.longs[1] = server_time(x, display)
    event.message.data.longs[2] = previous or 0
    if not x.XSendEvent(display, x.XDefaultRootWindow(display), False, (1 << 20) | (1 << 19), C.byref(event)):
        raise RuntimeError("Window-manager activation request was not sent")
    x.XFlush(display)
    until = time.monotonic() + 3
    while time.monotonic() < until:
        if active_window(x, display) == window:
            return
        pump()
    raise RuntimeError(f"Compositor did not activate test window: target={window}, active={active_window(x, display)}")
