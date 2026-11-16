#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real WebKit input on PRIVATE Xvfb + IBus. Not Firefox/Wayland acceptance.

Reuses the browser fixture: values/events reported by the page in its visible
window title; all typing/focus changes use XTest, never DOM injection.
"""
from pathlib import Path
import ctypes as C
import json
import os
import sys
import time
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
import private_bus  # noqa: E402


def inside():
    from zkey.runtime import isolated_engine
    with isolated_engine() as (env, _bus, _children):
        os.environ.update(env)
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        gi.require_version('GdkX11', '3.0')
        gi.require_version('WebKit2', '4.1')
        from gi.repository import Gdk, GdkX11, GLib, GObject, Gtk, WebKit2
        if not Gtk.init_check([])[0]:
            print('NOT_MEASURABLE: private display unavailable')
            return 2
        window = Gtk.Window(title='zkey WebKit input acceptance')
        window.set_default_size(720, 300)
        view = WebKit2.WebView.new_with_context(WebKit2.WebContext.new_ephemeral())
        window.add(view)
        window.show_all()
        errors = []
        edits = []  # Metadata only; never record text supplied to the IM context.
        im = view.get_input_method_context()
        if im is not None:
            im.connect('delete-surrounding', lambda _im, offset, count: edits.append(('delete', offset, count)))
            im.connect('committed', lambda _im, text: edits.append(('commit-length', len(text))))
        print(f'WebKit input context: {type(im).__name__}', flush=True)
        if os.environ.get('ZKEY_WEBKIT_DIAGNOSTIC_BRIDGE') == '1':
            # Root-cause experiment ONLY, not a product workaround: connect the
            # signal missing in WebKit's GTK wrapper, leaving all input as real
            # XTest keys. Never install/modify the system WebKit library.
            def observe(context):
                if isinstance(context, Gtk.IMMulticontext):
                    signal = GObject.signal_lookup('delete-surrounding', Gtk.IMContext)
                    if not GObject.signal_has_handler_pending(context, signal, 0, True):
                        def forward(_context, offset, count):
                            im.emit('delete-surrounding', offset, count)
                            return True
                        context.connect('delete-surrounding', forward)
                        print('DIAGNOSTIC ONLY: missing GTK-to-WebKit delete signal connected', flush=True)
                return True
            GObject.add_emission_hook(Gtk.IMContext, 'retrieve-surrounding', observe)
        view.connect('load-failed', lambda _v, _event, _uri, error: errors.append(error.message) or False)
        view.connect('notify::title', lambda v, _p: window.set_title(v.get_title() or 'zkey WebKit'))
        view.load_uri((ROOT / 'scripts/fixtures/browser-input.html').as_uri())
        main = GLib.MainContext.default()

        def pump(seconds=0.05):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while main.pending():
                    main.iteration(False)
                time.sleep(0.002)

        def state():
            title = view.get_title() or ''
            marker = 'zkey-browser-probe|'
            if not title.startswith(marker) or title.endswith('|start'):
                return {}
            return json.loads(unquote(title[len(marker):]))

        def expect(field, expected):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                pump()
                if errors:
                    raise RuntimeError('; '.join(errors))
                if state().get(field) == expected:
                    return state()
            trace = ROOT / '.tmp' / (Path(env['IBUS_ADDRESS'].split('unix:path=', 1)[1]).parent.name + '.log')
            raise AssertionError(f'WebKit page {field}: expected={expected!r}, actual={state().get(field)!r}; '
                                 f'edits={edits}; trace={trace.name}')

        x, t = C.CDLL('libX11.so.6'), C.CDLL('libXtst.so.6')
        x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        x.XGetInputFocus.argtypes = [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]
        x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
        x.XFlush.argtypes = [C.c_void_p]
        x.XCloseDisplay.argtypes = [C.c_void_p]
        t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        display = x.XOpenDisplay(os.environ['DISPLAY'].encode())
        if not display:
            raise RuntimeError('XTest display unavailable')
        try:
            pump(1)
            xid = GdkX11.X11Window.get_xid(window.get_window())
            x.XSetInputFocus(display, xid, 2, 0)
            x.XFlush(display)
            view.grab_focus()
            expect('focus', 'text')

            def send(name):
                focused, revert = C.c_ulong(), C.c_int()
                x.XGetInputFocus(display, C.byref(focused), C.byref(revert))
                if focused.value != xid:
                    raise RuntimeError('focus left the private WebKit window')
                code = x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode()))
                if not code:
                    raise RuntimeError(f'key unavailable: {name}')
                t.XTestFakeKeyEvent(display, code, True, 0)
                t.XTestFakeKeyEvent(display, code, False, 0)
                x.XFlush(display)
                pump()

            failures = []
            try:
                for key, expected in zip('tieengs', ('t', 'ti', 'tie', 'tiê', 'tiên', 'tiêng', 'tiếng')):
                    send(key)
                    expect('text', expected)
                for key in ['space', *'vieetj']:
                    send(key)
                expect('text', 'tiếng việt')
                send('BackSpace')
                expect('text', 'tiếng việ')
                send('t')
                expect('text', 'tiếng việt')
            except AssertionError as error:
                # Still measure the independent password field, but keep the
                # overall gate RED and explicitly report skipped text checks.
                failures.append(str(error))
                print(f'FAIL text; remaining text checks skipped: {error}', flush=True)
            send('Tab')
            expect('focus', 'secret')
            for key in 'aas':  # Synthetic only; must not become Telex.
                send(key)
            result = expect('secret', 'aas')
            snapshot = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                                window.get_allocated_width(), window.get_allocated_height())
            if snapshot is None:
                raise AssertionError('WebKit evidence screenshot unavailable')
            snapshot.savev(str(ROOT / '.tmp/webkit-input.png'), 'png', [], [])
            if result['compText'] or result['compSecret'] or result['inputs'] < 7:
                raise AssertionError('composition reached page or input-event evidence missing')
            log = ROOT / '.tmp' / (Path(env['IBUS_ADDRESS'].split('unix:path=', 1)[1]).parent.name + '.log')
            trace = log.read_text()
            seen = trace.count('key-state ')
            if seen < 4 or 'purpose=8' not in trace:
                raise AssertionError(f'private engine/password purpose evidence missing: {seen} keys')
            print(f'PASS WebKit password: synthetic keys unchanged; no composition; '
                  f'purpose PASSWORD seen; trace={log.name}')
            if failures:
                print('WEBKIT FAILED: ' + '; '.join(failures))
                return 1
            print(f'PASS WebKit: 7 prefixes, phrase, native Backspace, password unchanged; '
                  f'0 composition events; {result["inputs"]} input events; {seen} engine keys; trace={log.name}')
            return 0
        finally:
            x.XCloseDisplay(display)
            window.destroy()


def main():
    if sys.argv[1:] == ['--inside']:
        try:
            return inside()
        except AssertionError as error:
            print(f'WEBKIT FAILED: {error}')
            return 1
        except (OSError, RuntimeError, ValueError) as error:
            print(f'NOT_MEASURABLE: {error}')
            return 2
    display = os.environ.get('ZKEY_TEST_DISPLAY')
    if not display:
        print('NOT_MEASURABLE: needs private ZKEY_TEST_DISPLAY, never desktop')
        return 2
    env = dict(os.environ, DISPLAY=display, GDK_BACKEND='x11', GTK_IM_MODULE='ibus',
               ZKEY_ISOLATED_BUS='1', ZKEY_TRACE='1', GIO_USE_VFS='local', NO_AT_BRIDGE='1',
               WEBKIT_DISABLE_COMPOSITING_MODE='1', WEBKIT_DISABLE_DMABUF_RENDERER='1',
               LIBGL_ALWAYS_SOFTWARE='1')
    env.pop('IBUS_USE_PORTAL', None)
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), '--inside'], env)


if __name__ == '__main__':
    code = main()
    print(f'GATE_EXIT={code}', flush=True)
    raise SystemExit(code)
