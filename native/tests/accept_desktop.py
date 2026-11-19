#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native binary, real GTK3 widget and XTest keys on PRIVATE Xvfb only.

The test controller uses system Python/GI, not the product. Reuses ONLY the
workspace's required bus-isolation helper, never the legacy engine/core.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import ctypes as C
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import private_bus


def inside():
    import gi
    gi.require_version('IBus', '1.0')
    from gi.repository import Gio, GLib, IBus
    binary = ROOT / 'native/target/release/zkey-native'
    from provenance import verify
    try:source_info=verify(binary)
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        raise AssertionError(f'Native executable does not attest current source: {error}') from error
    with tempfile.TemporaryDirectory(prefix='native-ui-', dir=ROOT / '.tmp') as temporary:
        scratch = Path(temporary)
        for name in ('config','cache','data'):(scratch/name).mkdir(mode=0o700)
        env = dict(os.environ, IBUS_ADDRESS=f'unix:path={scratch}/ibus.sock',
                   IBUS_ADDRESS_FILE=str(scratch / 'address'), GTK_IM_MODULE='ibus',
                   IBUS_ENABLE_SYNC_MODE='1', ZKEY_NATIVE_TRACE='1',
                   ZKEY_NATIVE_READY=str(scratch / 'ready'),XDG_CONFIG_HOME=str(scratch/'config'),
                   XDG_CACHE_HOME=str(scratch/'cache'),XDG_DATA_HOME=str(scratch/'data'),GSETTINGS_BACKEND='memory',
                   ZKEY_NATIVE_CONFIG_PATH=str(scratch/'preferences.toml'))
        env.pop('IBUS_USE_PORTAL', None)
        os.environ.update(env)
        session_bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        session_bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
            'UpdateActivationEnvironment',GLib.Variant('(a{ss})',({k:env[k] for k in
                ('IBUS_ADDRESS','IBUS_ADDRESS_FILE','XDG_RUNTIME_DIR','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME') if k in env},)),
            None,Gio.DBusCallFlags.NONE,5000,None)
        children = []
        bridge=os.environ.get('ZKEY_NATIVE_WEBKIT_COMPAT')=='1'
        platform=('webkit-compat' if bridge else 'webkit') if os.environ.get('ZKEY_NATIVE_WEBKIT')=='1' else 'gtk4' if os.environ.get('ZKEY_NATIVE_GTK4')=='1' else 'gtk3'
        log_path = ROOT / f'.tmp/native-engine-{platform}-{"safe" if os.environ.get("ZKEY_NATIVE_SAFE_MODE")=="1" else "typing"}.log'
        with log_path.open('w') as log:
            try:
                if os.environ.get('ZKEY_NATIVE_COMPONENT_MODE') == '1':
                    components = scratch / 'component'
                    components.mkdir(mode=0o700)
                    flags = '' if os.environ.get('ZKEY_NATIVE_SAFE_MODE') == '1' else ' --experimental-rewrite'
                    (components / 'zkey-native.xml').write_text(
                        '<?xml version="1.0" encoding="utf-8"?>\n<component>\n'
                        '  <name>org.freedesktop.IBus.ZkeyNative</name>\n'
                        '  <description>zkey native</description>\n  <version>0.2.0-dev</version>\n'
                        '  <license>AGPL-3.0-or-later</license>\n  <author>zkey contributors</author>\n'
                        # ibus-daemon does not forward a child's stderr; the test needs the engine
                        # trace, so run it through `sh -c exec … >> log` (test fixture only).
                        + '  <exec>' + escape(f'/bin/sh -c "exec {binary} --ibus{flags} >> {log_path} 2>&1"')
                        + '</exec>\n  <textdomain>zkey-native</textdomain>\n'
                        '  <engines>\n    <engine>\n      <name>zkey-native</name>\n'
                        '      <longname>zkey native</longname>\n      <description>Vietnamese Telex</description>\n'
                        '      <language>vi</language>\n      <license>AGPL-3.0-or-later</license>\n'
                        '      <author>zkey contributors</author>\n      <icon>input-keyboard</icon>\n'
                        '      <layout>us</layout>\n    </engine>\n  </engines>\n</component>\n')
                    env['IBUS_COMPONENT_PATH'] = f'/usr/share/ibus/component:{components}'
                daemon = subprocess.Popen(['ibus-daemon', '--single', '--panel=disable', '--config=disable',
                    '--emoji-extension=disable', '--cache=none', f'--address={env["IBUS_ADDRESS"]}'],
                    env=env, stdout=log, stderr=log, start_new_session=True)
                children.append(daemon)
                until = time.monotonic() + 8
                while not (scratch / 'ibus.sock').exists():
                    if daemon.poll() is not None or time.monotonic() > until:
                        raise RuntimeError('Private IBus did not start')
                    time.sleep(.01)
                args = [str(binary), '--engine']
                if os.environ.get('ZKEY_NATIVE_SAFE_MODE') != '1':
                    args.append('--experimental-rewrite')
                if os.environ.get('ZKEY_NATIVE_COMPONENT_MODE') == '1':
                    # PRODUCTION path: no test-spawned engine and no RegisterComponent. The
                    # daemon itself starts `zkey-native --ibus` from a component XML when the
                    # engine is selected (same mechanism the installed component uses).
                    engine = None
                else:
                    engine = subprocess.Popen(args, env=env, stdout=log, stderr=log, start_new_session=True)
                    children.append(engine)
                    while not (scratch / 'ready').exists():
                        if engine.poll() is not None or time.monotonic() > until:
                            raise AssertionError(f'Native engine did not register; see {log_path}')
                        time.sleep(.01)
                IBus.init()
                bus = IBus.Bus.new()
                if not bus.set_global_engine('zkey-native'):
                    raise AssertionError('Native engine not selected on private daemon')
                gtk4=os.environ.get('ZKEY_NATIVE_GTK4')=='1'
                webkit=os.environ.get('ZKEY_NATIVE_WEBKIT')=='1'
                if gtk4 and webkit:raise RuntimeError('WebKit fixture uses GTK3')
                version='4.0' if gtk4 else '3.0'
                gi.require_version('Gtk', version)
                gi.require_version('Gdk', version)
                from gi.repository import Gdk, Gtk
                initialized=Gtk.init_check() if gtk4 else Gtk.init_check([])[0]
                if not initialized:
                    raise RuntimeError('No private GTK display')
                window = Gtk.Window(title='zkey-native — real keyboard test (synthetic only)')
                window.set_default_size(650, 220)
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
                if gtk4:
                    for setter in (box.set_margin_start,box.set_margin_end,box.set_margin_top,box.set_margin_bottom):setter(24)
                else:box.set_border_width(24)
                entry, password = Gtk.Entry(), Gtk.Entry()
                password.set_visibility(False)
                password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
                for w in (Gtk.Label(label='Rust native / system ABI / no legacy engine'), entry,
                          Gtk.Label(label='Synthetic password — must remain aas'), password):
                    if gtk4:box.append(w)
                    else:box.pack_start(w, False, False, 0)
                if gtk4:
                    window.set_child(box);window.present()
                else:
                    if webkit:
                        gi.require_version('WebKit2','4.1')
                        from gi.repository import WebKit2
                        view=WebKit2.WebView.new_with_context(WebKit2.WebContext.new_ephemeral())
                        window.add(view)
                        view.load_uri((ROOT/'scripts/fixtures/browser-input.html').as_uri())
                        def page():
                            title=view.get_title() or ''
                            marker='zkey-browser-probe|'
                            if not title.startswith(marker) or title.endswith('|start'):return {}
                            return json.loads(unquote(title[len(marker):]))
                        class Field:
                            def __init__(self,name):self.name=name
                            def get_text(self):return page().get(self.name,'')
                        entry,password=Field('text'),Field('secret')
                    else:window.add(box)
                    window.show_all()
                if webkit:view.grab_focus()
                else:entry.grab_focus()
                warnings, preedits = [], []
                handlers = [GLib.log_set_handler(domain, GLib.LogLevelFlags.LEVEL_WARNING | GLib.LogLevelFlags.LEVEL_CRITICAL,
                    lambda _d, _l, message, _data: warnings.append(message), None) for domain in ('Gtk','Gdk','IBUS')]
                if not webkit:
                    (entry.get_delegate() if gtk4 else entry).connect('preedit-changed', lambda _e, text: preedits.append(bool(text)))
                    (password.get_delegate() if gtk4 else password).connect('preedit-changed', lambda _e, text: preedits.append(bool(text)))
                main = GLib.MainContext.default()

                def engine_dead():
                    if engine is not None:
                        return engine.poll() is not None
                    # Component mode: the engine is the daemon's child running `--ibus`.
                    for entry in Path('/proc').iterdir():
                        if entry.name.isdigit():
                            try:
                                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                                cmdline = (entry / 'cmdline').read_bytes().split(b'\0')
                            except OSError:
                                continue
                            if int(fields[1]) == daemon.pid and b'--ibus' in cmdline:
                                return False
                    return True

                def pump(seconds=.08):
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        while main.pending():
                            main.iteration(False)
                        if engine_dead():
                            raise AssertionError('Native engine exited while typing')
                        time.sleep(.002)

                x, t = C.CDLL('libX11.so.6'), C.CDLL('libXtst.so.6')
                x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
                x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
                x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p,C.c_ulong], C.c_uint
                x.XSetInputFocus.argtypes = [C.c_void_p,C.c_ulong,C.c_int,C.c_ulong]
                x.XGetInputFocus.argtypes = [C.c_void_p,C.POINTER(C.c_ulong),C.POINTER(C.c_int)]
                x.XFlush.argtypes = [C.c_void_p]
                x.XCloseDisplay.argtypes = [C.c_void_p]
                t.XTestFakeKeyEvent.argtypes = [C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
                display = x.XOpenDisplay(os.environ['DISPLAY'].encode())
                if not display:
                    raise RuntimeError('XTest connection unavailable')
                pump(.3)
                from native_x11 import window_for_pid
                xid = window_for_pid(x,display,os.getpid())
                x.XSetInputFocus(display, xid, 2, 0)
                x.XFlush(display)
                pump(.6)
                if webkit and page().get('focus')!='text':raise RuntimeError('WebKit fixture is not ready with a visible focused field')

                def send(name,pause=.08):
                    focus, revert = C.c_ulong(), C.c_int()
                    x.XGetInputFocus(display,C.byref(focus),C.byref(revert))
                    if focus.value != xid:
                        raise RuntimeError('Focus left the private native test window')
                    code = x.XKeysymToKeycode(display,x.XStringToKeysym(name.encode()))
                    if not code:
                        raise RuntimeError('Required test keysym unavailable')
                    t.XTestFakeKeyEvent(display,code,True,0)
                    t.XTestFakeKeyEvent(display,code,False,0)
                    x.XFlush(display)
                    if pause:pump(pause)

                def expect(widget, text):
                    deadline = time.monotonic()+3
                    while widget.get_text()!=text and time.monotonic()<deadline:
                        pump()
                    if widget.get_text()!=text:
                        raise AssertionError(f'Synthetic widget expected {text!r}, actual {widget.get_text()!r}')

                try:
                    safe = os.environ.get('ZKEY_NATIVE_SAFE_MODE') == '1'
                    # Deliberate inverse control: ask a SAFE/bypass engine to
                    # satisfy the Telex oracle. It MUST fail, not always pass.
                    expected_safe=safe and os.environ.get('ZKEY_NATIVE_EXPECT_TELEX')!='1'
                    expected = ('t','ti','tie','tiee','tieen','tieeng','tieengs') if expected_safe else ('t','ti','tie','tiê','tiên','tiêng','tiếng')
                    for k, want in zip('tieengs',expected):
                        send(k);expect(entry,want)
                    send('space')
                    for k in 'vieetj':send(k)
                    expect(entry,'tieengs vieetj' if safe else 'tiếng việt')
                    send('BackSpace');send('t')
                    expect(entry,'tieengs vieett' if safe else 'tiếng việt')
                    burst_count=0
                    if not safe and (not webkit or bridge):
                        cases=[('tieengs vieetj','tiếng việt'),('vieetj\bt','việt'),('tieengs\bf','tiền')]
                        total=len(cases)*5
                        if not total:raise AssertionError('Empty native burst acceptance population')
                        ctrl=x.XKeysymToKeycode(display,x.XStringToKeysym(b'Control_L'))
                        for typed,wanted in cases:
                            for _ in range(5):
                                t.XTestFakeKeyEvent(display,ctrl,True,0);x.XFlush(display);send('a')
                                t.XTestFakeKeyEvent(display,ctrl,False,0);x.XFlush(display);send('BackSpace');expect(entry,'')
                                for key in typed:send({' ':'space','\b':'BackSpace'}.get(key,key),pause=0)
                                pump(.2);expect(entry,wanted);pump(.1);expect(entry,wanted);burst_count+=1
                        print(f'PASS native GTK{4 if gtk4 else 3} burst: {burst_count}/{total} zero-delay rounds with native Backspace')
                    send('Tab')
                    focused=window.get_focus()
                    password_focused=page().get('focus')=='secret' if webkit else focused is not None and (focused==password or focused.is_ancestor(password))
                    if not password_focused:raise AssertionError('Password did not receive native Tab focus')
                    for k in 'aas':send(k)
                    expect(password,'aas')
                    if webkit and bridge and not safe:
                        # Two real WebViews with distinct native IM contexts,
                        # then destroy one and continue in the survivor. This
                        # guards against a global 'last WebKit view' bridge.
                        first_xid=xid;first_text=entry.get_text()
                        other=Gtk.Window(title='zkey-native-isolation-second-view')
                        other.set_default_size(660,240)
                        second=WebKit2.WebView.new_with_context(WebKit2.WebContext.new_ephemeral())
                        other.add(second);other.show_all()
                        second.load_uri((ROOT/'scripts/fixtures/browser-input.html').as_uri())
                        def second_page():
                            title=second.get_title() or ''
                            if not title.startswith('zkey-browser-probe|') or title.endswith('|start'):return {}
                            return json.loads(unquote(title[len('zkey-browser-probe|'):]))
                        try:
                            deadline=time.monotonic()+8
                            while second_page().get('focus')!='text' and time.monotonic()<deadline:pump(.05)
                            if second_page().get('focus')!='text':raise RuntimeError('Second real WebKit view not ready')
                            xid=window_for_pid(x,display,os.getpid(),b'zkey-native-isolation-second-view')
                            x.XSetInputFocus(display,xid,2,0);x.XFlush(display);pump(.3)
                            for key in 'aas':send(key)
                            if second_page().get('text')!='ấ':raise AssertionError('Second WebKit view did not compose independently')
                            send('Tab')
                            for key in 'aas':send(key)
                            if second_page().get('secret')!='aas':raise AssertionError('Second WebKit password changed')
                            if entry.get_text()!=first_text or password.get_text()!='aas':raise AssertionError('WebKit bridge edited the wrong view')
                        finally:
                            other.destroy();pump(.2);xid=first_xid
                        x.XSetInputFocus(display,xid,2,0);x.XFlush(display);pump(.2)
                        shift=x.XKeysymToKeycode(display,x.XStringToKeysym(b'Shift_L'))
                        t.XTestFakeKeyEvent(display,shift,True,0);x.XFlush(display);send('Tab')
                        t.XTestFakeKeyEvent(display,shift,False,0);x.XFlush(display);pump(.1)
                        if page().get('focus')!='text':raise AssertionError('Surviving WebKit view did not recover actual focus')
                        ctrl=x.XKeysymToKeycode(display,x.XStringToKeysym(b'Control_L'))
                        t.XTestFakeKeyEvent(display,ctrl,True,0);x.XFlush(display);send('a')
                        t.XTestFakeKeyEvent(display,ctrl,False,0);x.XFlush(display);send('BackSpace');expect(entry,'')
                        for key in 'hoaf':send(key)
                        expect(entry,'hoà');expect(password,'aas')
                        print('PASS WebKit compatibility: 2 distinct views/passwords isolated; destroyed-view cleanup; survivor continues typing')
                    if any(preedits):raise AssertionError('Visible preedit appeared')
                    if webkit and (page().get('compText') or page().get('compSecret')):raise AssertionError('WebKit page received composition events')
                    if warnings:raise AssertionError(f'GTK warnings/errors: {warnings}')
                    image=ROOT/f'.tmp/native-{platform}-{"safe" if safe else "typing"}.png'
                    subprocess.run([sys.executable,str(ROOT/'native/tests/capture.py'),str(image)],env=os.environ.copy(),check=True)
                    log.flush()
                    trace=log_path.read_text()
                    build_info=verify(binary)
                    if build_info!=source_info:raise AssertionError('Source or executable changed during UI acceptance')
                    if f'build_source_sha256={build_info["source_sha256"]}' not in trace:
                        raise AssertionError('Native engine trace and executable build source do not match')
                    if trace.count('key-event')<7:raise AssertionError('Missing native key-event evidence')
                    # GTK3 may bypass its IM context entirely for a password,
                    # so it need not forward ContentType=PASSWORD to the engine.
                    # Require the actual focus-out guard instead of inventing
                    # a purpose callback that did not occur on this route.
                    if not any(line.startswith('zkey-native: context-state event=FocusOut') and 'protected=true' in line
                               for line in trace.splitlines()):
                        raise AssertionError('Engine did not close the previous context on password focus')
                    if os.environ.get('ZKEY_NATIVE_SETTINGS')=='1':
                        if gtk4 or webkit or safe:raise RuntimeError('Settings role test uses the GTK3 experimental fixture')
                        from ui_settings import exercise
                        exercise(env,pump,display,x,t,window,entry,send,expect,xid)
                    (ROOT/f'.tmp/native-evidence-{platform}-{"safe" if safe else "typing"}.json').write_text(json.dumps({
                        'status':'pass','build':build_info,'frontend':platform,'safe_bypass':safe,'webkit_compat':bridge,'prefixes':7,
                        'burst_rounds':burst_count,'trace':log_path.name,'screenshot':image.name},indent=2)+'\n')
                    print(f'PASS native {"WebKit" if webkit else "GTK4" if gtk4 else "GTK3"}: safe={safe}; 7 prefixes, phrase, Backspace, password unchanged, no visible preedit or GTK log-handler warnings')
                    return 0
                except AssertionError:
                    if webkit:
                        subprocess.run([sys.executable,str(ROOT/'native/tests/capture.py'),str(ROOT/'.tmp/native-webkit-failed.png')],env=os.environ.copy(),check=True)
                    raise
                finally:
                    x.XCloseDisplay(display)
                    window.destroy()
                    for domain, handler in zip(('Gtk','Gdk','IBUS'),handlers):GLib.log_remove_handler(domain,handler)
            finally:
                for child in reversed(children):
                    if child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
                    try:child.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL)
                        child.wait()


def main():
    if sys.argv[1:] == ['--inside']:
        try:return inside()
        except AssertionError as error:
            print(f'NATIVE FAILED: {error}');return 1
        except (OSError,RuntimeError,ValueError) as error:
            print(f'NOT_MEASURABLE: {error}');return 2
    display=os.environ.get('ZKEY_TEST_DISPLAY')
    if not display:
        print('NOT_MEASURABLE: requires PRIVATE ZKEY_TEST_DISPLAY');return 2
    env=dict(os.environ,DISPLAY=display,GDK_BACKEND='x11',GIO_USE_VFS='local',NO_AT_BRIDGE='1',
             WEBKIT_DISABLE_COMPOSITING_MODE='1',WEBKIT_DISABLE_DMABUF_RENDERER='1')
    if env.get('ZKEY_NATIVE_GTK4')=='1':
        # Xvfb has no GPU/DRI3. Select software rendering, not suppressed errors.
        env.update(GSK_RENDERER='cairo',GDK_DISABLE='gl,vulkan')
    env.pop('IBUS_USE_PORTAL',None)
    # This entrypoint deliberately owns a NEW engine/bus for frontend isolation,
    # even when launched through the product to verify its embedded bridge.
    # Do not certify the outer runtime by accidentally inheriting its root.
    env.pop('ZKEY_NATIVE_SESSION_ROOT',None)
    return private_bus.call([sys.executable,str(Path(__file__).resolve()),'--inside'],env)


if __name__=='__main__':
    result=main();print(f'GATE_EXIT={result}',flush=True);raise SystemExit(result)
