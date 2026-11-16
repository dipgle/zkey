# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings role A -> real typing role B. Only XTest creates valid settings.

Exception: malformed configuration is injected on disk ONLY as a fault fixture
to exercise recovery. The positive configuration is created by clicks on the UI.
"""
from pathlib import Path
import ctypes as C
import os
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import editor_ui  # read-only accessibility inspector, NOT the legacy engine


def exercise(env,pump,display,x,t,window,entry,send,expect,xid):
    config=Path(env['ZKEY_NATIVE_CONFIG_PATH'])
    x.XDefaultRootWindow.argtypes,x.XDefaultRootWindow.restype=[C.c_void_p],C.c_ulong
    x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
    x.XFetchName.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_void_p)]
    x.XInternAtom.argtypes,x.XInternAtom.restype=[C.c_void_p,C.c_char_p,C.c_int],C.c_ulong
    x.XGetWindowProperty.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_void_p)]
    x.XFree.argtypes=[C.c_void_p]
    t.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
    t.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]

    def focus_entry():
        x.XSetInputFocus(display,xid,2,0);x.XFlush(display);pump(.2)
        for _ in range(3):
            if entry.has_focus():return
            send('Tab')
        raise AssertionError('Could not return to the real typing field')

    def word():
        focus_entry()
        control=x.XKeysymToKeycode(display,x.XStringToKeysym(b'Control_L'))
        t.XTestFakeKeyEvent(display,control,True,0);x.XFlush(display)
        send('a')
        t.XTestFakeKeyEvent(display,control,False,0);x.XFlush(display)
        send('BackSpace');expect(entry,'')
        for key in 'hoaf':send(key)
        return entry.get_text()

    if word()!='hoà':raise AssertionError('Default modern tone was not visible before settings')
    # Fault injection, NOT a way of creating the positive acceptance settings.
    config.write_text('schema = broken\n')
    processes=[]
    log=(ROOT/'.tmp/native-settings.log').open('w')
    settings_env=dict(env,GTK_IM_MODULE='gtk-im-context-simple')
    settings_env.pop('NO_AT_BRIDGE',None)

    def screenshot(name):
        subprocess.run([sys.executable,str(ROOT/'native/tests/capture.py'),str(ROOT/f'.tmp/native-settings-{name}.png')],env=settings_env,check=True)

    def find_xid():
        root=x.XDefaultRootWindow(display)
        parent,child_root,children,count=C.c_ulong(),C.c_ulong(),C.POINTER(C.c_ulong)(),C.c_uint()
        if not x.XQueryTree(display,root,C.byref(child_root),C.byref(parent),C.byref(children),C.byref(count)):
            raise RuntimeError('Cannot inspect private X window tree')
        try:
            for i in range(count.value):
                name=C.c_void_p()
                if x.XFetchName(display,children[i],C.byref(name)) and name.value:
                    try:
                        # XFetchName may expose COMPOUND_TEXT rather than UTF-8.
                        # The ASCII prefix is unique on this private fixture
                        # display; the accessibility tree already pins the PID.
                        if C.string_at(name).startswith(b'zkey native'):
                            return children[i]
                    finally:x.XFree(name)
                actual,fmt,count,remaining,data=C.c_ulong(),C.c_int(),C.c_ulong(),C.c_ulong(),C.c_void_p()
                atom=x.XInternAtom(display,b'_NET_WM_NAME',False)
                result=x.XGetWindowProperty(display,children[i],atom,0,512,False,0,C.byref(actual),C.byref(fmt),C.byref(count),C.byref(remaining),C.byref(data))
                try:
                    if result==0 and data.value and fmt.value==8 and C.string_at(data,count.value).startswith(b'zkey native'):
                        return children[i]
                finally:
                    if data.value:x.XFree(data)
        finally:
            if children:x.XFree(children)
        raise RuntimeError('Native settings window is not mapped')

    def open_settings():
        process=subprocess.Popen([str(ROOT/'native/target/release/zkey-native'),'--settings'],env=settings_env,stdout=log,stderr=log)
        processes.append(process)
        Atspi,app=editor_ui.connect(process.pid)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            nodes=list(editor_ui.walk(app))
            modern=next((n for n in nodes if n.get_role()==Atspi.Role.CHECK_BOX and 'hiện đại' in n.get_name()),None)
            if modern is not None:break
            pump(.05)
        else:raise RuntimeError('Native settings controls were not exposed by the visible UI')
        controls={}
        for node in nodes:
            role,name=node.get_role(),node.get_name() or ''
            if role==Atspi.Role.CHECK_BOX and 'hiện đại' in name:controls['modern']=node
            elif role==Atspi.Role.CHECK_BOX and 'sửa surrounding' in name:controls['experimental']=node
            elif role==Atspi.Role.CHECK_BOX and 'Cầu nối WebKit' in name:controls['webkit']=node
            elif role==Atspi.Role.PUSH_BUTTON and name=='Lưu thiết lập':controls['save']=node
            elif role==Atspi.Role.PUSH_BUTTON and name=='Đóng':controls['close']=node
        if set(controls)!={'modern','experimental','webkit','save','close'}:raise AssertionError('Native settings UI controls are incomplete')
        deadline=time.monotonic()+3
        while True:
            try:top=find_xid();break
            except RuntimeError:
                if time.monotonic()>=deadline:
                    screenshot('unmapped')
                    raise
                pump(.1)
        x.XSetInputFocus(display,top,2,0);x.XFlush(display);pump(.2)
        return process,Atspi,app,controls

    def checked(Atspi,node):
        node.clear_cache();return node.get_state_set().contains(Atspi.StateType.CHECKED)

    def click(Atspi,node):
        bounds=node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
        if bounds.width<=0 or bounds.height<=0:raise AssertionError('Target control has no visible bounds')
        t.XTestFakeMotionEvent(display,-1,bounds.x+bounds.width//2,bounds.y+bounds.height//2,0)
        t.XTestFakeButtonEvent(display,1,True,0);t.XTestFakeButtonEvent(display,1,False,0);x.XFlush(display);pump(.25)

    def labels(Atspi,app):
        return [node.get_name() or '' for node in editor_ui.walk(app) if node.get_role()==Atspi.Role.LABEL]

    try:
        process,Atspi,app,controls=open_settings()
        if not any('Cấu hình lỗi' in text for text in labels(Atspi,app)):raise AssertionError('Broken-file error is not visible')
        if config.read_text()!='schema = broken\n':raise AssertionError('Opening settings silently overwrote the broken file')
        screenshot('error')
        if not checked(Atspi,controls['modern']):raise AssertionError('Recovery defaults are not modern')
        click(Atspi,controls['modern']);click(Atspi,controls['experimental']);click(Atspi,controls['webkit']);click(Atspi,controls['save'])
        if not any(text.startswith('Đã lưu.') for text in labels(Atspi,app)):raise AssertionError('Save was not acknowledged by the visible screen')
        data=tomllib.loads(config.read_text())
        if data['tone_style']!='traditional' or not data['experimental_rewrite'] or not data['webkit_compat']:raise AssertionError('UI choices did not reach the actual TOML data')
        journal=config.with_name('changes.log').read_text()
        if f'commit {data["generation"]}' not in journal:raise AssertionError('Saved settings lack their audit commit')
        screenshot('saved')
        click(Atspi,controls['close']);process.wait(timeout=5)
        if process.returncode:raise AssertionError('Settings exited with an error')
        process,Atspi,app,controls=open_settings()
        if checked(Atspi,controls['modern']) or not checked(Atspi,controls['experimental']) or not checked(Atspi,controls['webkit']):raise AssertionError('Reopened UI lost the actual saved choices')
        screenshot('reopened');click(Atspi,controls['close']);process.wait(timeout=5)
        if word()!='hòa':raise AssertionError('Settings UI -> typing UI did not apply traditional tone placement')
        # Fault-inject an unavailable application. The real GUI launch path
        # must show a dismissible error rather than disappear with Terminal=false.
        with tempfile.TemporaryDirectory(prefix='nr-',dir=ROOT/'.tmp') as runtime:
            failure_env=dict(settings_env,XDG_RUNTIME_DIR=runtime)
            failure_env.pop('ZKEY_TEST_DISPLAY',None)  # exercise the NORMAL dialog path on our private Xvfb
            process=subprocess.Popen([str(ROOT/'native/target/release/zkey-native'),'--run','/zkey-test/nonexistent-application'],
                                     env=failure_env,stdout=log,stderr=log)
            processes.append(process)
            Atspi,app=editor_ui.connect(process.pid)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                nodes=list(editor_ui.walk(app))
                close=next((n for n in nodes if n.get_role()==Atspi.Role.PUSH_BUTTON and n.get_name()=='Đóng'),None)
                if close is not None:break
                pump(.05)
            else:raise AssertionError('Failed native startup did not expose its error dialog')
            if not any('Không khởi động được zkey native' in text for text in labels(Atspi,app)):
                raise AssertionError('Native startup failure is not visible in the actual dialog')
            x.XSetInputFocus(display,find_xid(),2,0);x.XFlush(display);pump(.15)
            screenshot('startup-error');click(Atspi,close);process.wait(timeout=5)
            if process.returncode!=1:raise AssertionError('Expected failed startup did not retain failure exit1')
        log.flush()
        diagnostics=(ROOT/'.tmp/native-settings.log').read_text()
        if any(marker in diagnostics for marker in ('CRITICAL','WARNING','panicked')):raise AssertionError('Native settings emitted warnings/errors')
        print('PASS native settings: error/recovery; clicks -> TOML + audit; reopen; typing hoà -> hòa; real startup-failure dialog + exit1')
    finally:
        for process in processes:
            if process.poll() is None:process.terminate();process.wait(timeout=5)
        log.close()
