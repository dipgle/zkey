# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test-only PUBLIC Xlib window ownership lookup; no deprecated GTK4 XID API."""
import ctypes as C
import os


def window_for_pid(x,display,pid,title_prefix=b'zkey-native'):
    if not os.environ.get('ZKEY_TEST_DISPLAY') or os.environ.get('DISPLAY')!=os.environ['ZKEY_TEST_DISPLAY']:
        raise RuntimeError('Window lookup is confined to the private test display')
    x.XDefaultRootWindow.argtypes,x.XDefaultRootWindow.restype=[C.c_void_p],C.c_ulong
    x.XInternAtom.argtypes,x.XInternAtom.restype=[C.c_void_p,C.c_char_p,C.c_int],C.c_ulong
    x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
    x.XGetWindowProperty.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_void_p)]
    x.XFree.argtypes=[C.c_void_p]
    root=x.XDefaultRootWindow(display)
    parent,child_root,children,count=C.c_ulong(),C.c_ulong(),C.POINTER(C.c_ulong)(),C.c_uint()
    if not x.XQueryTree(display,root,C.byref(child_root),C.byref(parent),C.byref(children),C.byref(count)):
        raise RuntimeError('Cannot inspect private root windows')
    def prop(window,name):
        actual,fmt,n,remaining,data=C.c_ulong(),C.c_int(),C.c_ulong(),C.c_ulong(),C.c_void_p()
        code=x.XGetWindowProperty(display,window,x.XInternAtom(display,name,False),0,512,False,0,C.byref(actual),C.byref(fmt),C.byref(n),C.byref(remaining),C.byref(data))
        try:
            if code or not data.value:return None
            if fmt.value==32:return list(C.cast(data,C.POINTER(C.c_ulong))[:n.value])
            if fmt.value==8:return C.string_at(data,n.value)
            return None
        finally:
            if data.value:x.XFree(data)
    try:
        for i in range(count.value):
            window=children[i]
            name=prop(window,b'_NET_WM_NAME')
            if prop(window,b'_NET_WM_PID')==[pid] and isinstance(name,bytes) and name.startswith(title_prefix):return window
    finally:
        if children:x.XFree(children)
    raise RuntimeError('No private test window for the expected process/title')
