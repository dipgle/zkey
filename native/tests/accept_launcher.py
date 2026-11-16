#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An actual GTK client opened by the NATIVE launcher, not a Python runtime.

All data comes from XTest keys on a private display. This controller is a test
dependency, not shipped in the native product. No direct InputContext writes.
"""
from pathlib import Path
import ctypes as C
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]


def run():
    if not os.environ.get('ZKEY_TEST_DISPLAY') or os.environ.get('DISPLAY')!=os.environ['ZKEY_TEST_DISPLAY']:
        print('NOT_MEASURABLE: private test display required');return 2
    session=Path(os.environ['ZKEY_NATIVE_SESSION_ROOT']).resolve()
    if not session.is_relative_to(ROOT/'.tmp'):raise RuntimeError('Acceptance must not write outside project scratch')
    import gi
    gi.require_version('Gtk','3.0')
    gi.require_version('GdkX11','3.0')
    gi.require_version('IBus','1.0')
    from gi.repository import GdkX11,GLib,Gtk,IBus
    IBus.init()
    engine=IBus.Bus.new().get_global_engine()
    if engine is None or engine.get_name()!='zkey-native':raise AssertionError('Launcher did not select its native engine')
    if not Gtk.init_check([])[0]:return 2
    window=Gtk.Window(title='zkey native launcher acceptance — synthetic only')
    window.set_default_size(660,230)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);box.set_border_width(24)
    text,password=Gtk.Entry(),Gtk.Entry()
    password.set_visibility(False);password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    for widget in (Gtk.Label(label='Native launcher → native IBus → real GTK client'),text,Gtk.Label(label='Synthetic password'),password):
        box.pack_start(widget,False,False,0)
    window.add(box);window.show_all();text.grab_focus()
    main=GLib.MainContext.default()
    warnings=[]
    handlers=[GLib.log_set_handler(domain,GLib.LogLevelFlags.LEVEL_CRITICAL|GLib.LogLevelFlags.LEVEL_WARNING,
        lambda _d,_l,message,_u:warnings.append(message),None) for domain in ('Gtk','Gdk','IBUS','VTE')]
    def pump(seconds=.03):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            while main.pending():main.iteration(False)
            time.sleep(.001)
    x,t=C.CDLL('libX11.so.6'),C.CDLL('libXtst.so.6')
    x.XOpenDisplay.argtypes,x.XOpenDisplay.restype=[C.c_char_p],C.c_void_p
    x.XStringToKeysym.argtypes,x.XStringToKeysym.restype=[C.c_char_p],C.c_ulong
    x.XKeysymToKeycode.argtypes,x.XKeysymToKeycode.restype=[C.c_void_p,C.c_ulong],C.c_uint
    x.XSetInputFocus.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_ulong]
    x.XGetInputFocus.argtypes=[C.c_void_p,C.POINTER(C.c_ulong),C.POINTER(C.c_int)]
    x.XFlush.argtypes=[C.c_void_p];x.XCloseDisplay.argtypes=[C.c_void_p]
    t.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
    display=x.XOpenDisplay(os.environ['DISPLAY'].encode())
    if not display:raise RuntimeError('Private XTest connection unavailable')
    pump(.3);xid=GdkX11.X11Window.get_xid(window.get_window())
    x.XSetInputFocus(display,xid,2,0);x.XFlush(display);pump(.2)
    def key(name,pause=.025,control=False):
        focus,revert=C.c_ulong(),C.c_int()
        x.XGetInputFocus(display,C.byref(focus),C.byref(revert))
        if focus.value!=xid:raise RuntimeError('Focus escaped the native launcher test window')
        code=x.XKeysymToKeycode(display,x.XStringToKeysym(name.encode()))
        ctrl=x.XKeysymToKeycode(display,x.XStringToKeysym(b'Control_L'))
        if not code:raise RuntimeError('Synthetic key unavailable')
        if control:t.XTestFakeKeyEvent(display,ctrl,True,0)
        t.XTestFakeKeyEvent(display,code,True,0);t.XTestFakeKeyEvent(display,code,False,0)
        if control:t.XTestFakeKeyEvent(display,ctrl,False,0)
        x.XFlush(display)
        if pause:pump(pause)
    def expect(widget,wanted):
        until=time.monotonic()+3
        while time.monotonic()<until and widget.get_text()!=wanted:pump(.01)
        if widget.get_text()!=wanted:raise AssertionError(f'Synthetic UI expected {wanted!r}, got {widget.get_text()!r}')
    def clear():key('a',control=True);key('BackSpace');expect(text,'')
    try:
        for k,wanted in zip('tieengs',('t','ti','tie','tiê','tiên','tiêng','tiếng')):key(k);expect(text,wanted)
        names={' ':'space','\b':'BackSpace'}
        cases=[('tieengs vieetj','tiếng việt'),('vieetj\bt','việt'),('tieengs\bf','tiền')]
        count=0
        rounds=5;total=len(cases)*rounds
        if not total:raise AssertionError('Native burst acceptance population is empty')
        for typed,wanted in cases:
            clear()
            for k in typed:key(names.get(k,k),pause=.08)
            expect(text,wanted)
            for _ in range(rounds):
                clear()
                for k in typed:key(names.get(k,k),pause=0)
                expect(text,wanted);count+=1
        clear();key('u');key('Control_L');key('s');expect(text,'us')
        clear();key('a');key('a');key('Control_L');key('s');expect(text,'âs');key('Escape');expect(text,'âs')
        key('Tab')
        if not password.has_focus():raise AssertionError('Native password focus missing')
        for k in 'aas':key(k)
        expect(password,'aas')
        if os.environ.get('ZKEY_NATIVE_HEALTH_FAULT')=='1':
            from health_fault import exercise
            exercise(window,text,password,key,expect,pump,x,t,display,xid)
        if os.environ.get('ZKEY_NATIVE_VTE')=='1':
            gi.require_version('Vte','2.91')
            from gi.repository import Vte
            terminal=Vte.Terminal();terminal.set_size_request(-1,120)
            box.pack_start(terminal,True,True,0);window.resize(660,430);window.show_all()
            spawned=[]
            # Synthetic secret ONLY. It is entered by keys, not fed into the
            # PTY/API. The child compares but never prints or logs its value.
            script="printf 'ready\\n'; IFS= read -r -s -n 3 secret; if [ \"$secret\" = aas ]; then printf '\\nsame\\n'; else printf '\\ndifferent\\n'; fi; unset secret; sleep .2"
            shell_env=[f'{k}={v}' for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','HOME')]
            terminal.spawn_async(Vte.PtyFlags.DEFAULT,str(session),['/bin/bash','--norc','--noprofile','-c',script],shell_env,
                GLib.SpawnFlags.DEFAULT,None,None,-1,None,lambda _t,pid,error,*_:spawned.append((pid,error)))
            def screen():
                value=terminal.get_text_format(Vte.Format.TEXT)
                if value is None:raise RuntimeError('Cannot read the actual VTE screen')
                return value
            until=time.monotonic()+5
            while time.monotonic()<until and (not spawned or 'ready' not in screen()):pump(.03)
            if not spawned or spawned[0][1] is not None:raise RuntimeError('Native VTE fixture child did not start')
            if 'ready' not in screen():raise AssertionError('VTE did not show its secret prompt')
            key('Tab')
            if not terminal.has_focus():raise AssertionError('Real Tab did not focus the native VTE fixture')
            key('a');key('a')
            if screen().split('ready',1)[1].strip():raise AssertionError('ECHO-off VTE displayed synthetic secret text')
            subprocess.run([sys.executable,str(ROOT/'native/tests/capture.py'),str(ROOT/'.tmp/native-terminal-secret.png')],check=True)
            key('s');until=time.monotonic()+4
            while time.monotonic()<until and 'same' not in screen() and 'different' not in screen():pump(.03)
            if 'same' not in screen() or 'different' in screen():raise AssertionError('Native engine changed the synthetic ECHO-off secret')
            print('PASS native VTE: ECHO-off synthetic secret invisible and unchanged; not terminal Telex support')
        if warnings:raise AssertionError(f'Native GTK client warnings: {warnings}')
        subprocess.run([sys.executable,str(ROOT/'native/tests/capture.py'),str(ROOT/'.tmp/native-launcher.png')],check=True)
        trace=(session/'engine.log').read_text()
        source_info=json.loads(os.environ['ZKEY_NATIVE_ACCEPT_BUILD'])
        if f'build_source_sha256={source_info["source_sha256"]}' not in trace:
            raise AssertionError('Actual native engine does not match the independently attested source')
        if trace.count('key-event')<7:raise AssertionError('Missing native engine key-event trace')
        if any(marker in trace for marker in ('CRITICAL','WARNING','panicked')):raise AssertionError('Native engine log contains warnings/errors')
        (ROOT/'.tmp/native-launcher-engine.log').write_text(trace)
        print(f'PASS native launcher: own bus/IBus/binary; 7 prefixes; {count}/{total} zero-delay burst rounds; Ctrl freeze; password unchanged')
        return 0
    except AssertionError:
        subprocess.run([sys.executable,str(ROOT/'native/tests/capture.py'),str(ROOT/'.tmp/native-launcher-failed.png')],check=True)
        (ROOT/'.tmp/native-launcher-engine.log').write_text((session/'engine.log').read_text())
        raise
    finally:
        x.XCloseDisplay(display);window.destroy()
        for domain,handler in zip(('Gtk','Gdk','IBUS','VTE'),handlers):GLib.log_remove_handler(domain,handler)


def main():
    if sys.argv[1:]!=['--inside']:
        if not os.environ.get('ZKEY_TEST_DISPLAY') or os.environ.get('DISPLAY')!=os.environ['ZKEY_TEST_DISPLAY']:
            print('NOT_MEASURABLE: private test display required');return 2
        binary=Path(os.environ.get('ZKEY_NATIVE_BINARY',ROOT/'native/target/release/zkey-native'))
        from provenance import verify
        try:source_info=verify(binary)
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            print(f'NATIVE LAUNCHER FAILED: current-source attestation: {error}');return 1
        with tempfile.TemporaryDirectory(prefix='nl-config-',dir=ROOT/'.tmp') as temporary:
            config=Path(temporary)
            for name in ('config','cache','data'):(config/name).mkdir(mode=0o700)
            env=dict(os.environ,XDG_RUNTIME_DIR=str(ROOT/'.tmp'),XDG_CONFIG_HOME=str(config/'config'),
                     XDG_CACHE_HOME=str(config/'cache'),XDG_DATA_HOME=str(config/'data'),
                     ZKEY_NATIVE_CONFIG_PATH=str(config/'preferences.toml'),ZKEY_NATIVE_TRACE='1',
                     ZKEY_NATIVE_ACCEPT_BUILD=json.dumps(source_info))
            process=subprocess.run([str(binary),'--experimental-rewrite','--run',sys.executable,str(Path(__file__).resolve()),'--inside'],
                                   env=env,text=True,capture_output=True)
            print(process.stdout,end='');print(process.stderr,end='',file=sys.stderr)
            gates=[int(line.split('=',1)[1]) for line in process.stdout.splitlines() if line.startswith('GATE_EXIT=')]
            if not gates:return 1  # native product failed before its fixture started
            if gates[-1]!=0:return gates[-1]
            if verify(binary)!=source_info:
                print('NATIVE LAUNCHER FAILED: source/binary changed during acceptance');return 1
            return 0 if process.returncode==0 else 1  # cleanup failure must be RED
    try:code=run()
    except AssertionError as error:print(f'NATIVE LAUNCHER FAILED: {error}');code=1
    except (OSError,RuntimeError,ValueError) as error:print(f'NOT_MEASURABLE: {error}');code=2
    print(f'GATE_EXIT={code}',flush=True);return code


if __name__=='__main__':
    result=main();print(f'LAUNCHER_GATE_EXIT={result}',flush=True);raise SystemExit(result)
