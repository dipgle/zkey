# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings role A (command line) -> real typing role B (XTest keys into a real GTK entry).

Exception: malformed configuration is injected on disk ONLY as a fault fixture to
exercise recovery. Valid settings are created by `zkey-native --set` itself.
There is no settings window any more (no GUI toolkit); the startup-failure warning is
a desktop notification, captured by a test service on a PRIVATE bus.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'native/tests'))
from notify_sink import PrivateBus, Sink


def exercise(env, pump, display, x, t, window, entry, send, expect, xid):
    config = Path(env['ZKEY_NATIVE_CONFIG_PATH'])
    binary = str(ROOT / 'native/target/release/zkey-native')
    child_env = dict(env)
    child_env.pop('IBUS_ADDRESS', None)

    def cli(*arguments):
        return subprocess.run([binary, *arguments], env=child_env, capture_output=True, text=True, timeout=30)

    def focus_entry():
        x.XSetInputFocus(display, xid, 2, 0); x.XFlush(display); pump(.2)
        for _ in range(3):
            if entry.has_focus(): return
            send('Tab')
        raise AssertionError('Could not return to the real typing field')

    def word():
        focus_entry()
        import ctypes as C
        control = x.XKeysymToKeycode(display, x.XStringToKeysym(b'Control_L'))
        t.XTestFakeKeyEvent(display, control, True, 0); x.XFlush(display)
        send('a')
        t.XTestFakeKeyEvent(display, control, False, 0); x.XFlush(display)
        send('BackSpace'); expect(entry, '')
        for key in 'hoaf': send(key)
        return entry.get_text()

    if word() != 'hoà': raise AssertionError('Default modern tone was not visible before settings')

    # Fault injection, NOT a way of creating the positive acceptance settings.
    config.write_text('schema = broken\n')
    shown = cli('--show')
    if shown.returncode != 1 or 'Cấu hình lỗi' not in shown.stdout:
        raise AssertionError(f'Broken file not reported with exit 1: {shown.returncode} {shown.stdout!r}')
    if config.read_text() != 'schema = broken\n': raise AssertionError('--show silently overwrote the broken file')
    for bad in (['max_word_keys=3'], ['tone_style=sloppy'], ['nope=1'], ['enabled=true', 'enabled=false'], []):
        refused = cli('--set', *bad)
        if refused.returncode != 1: raise AssertionError(f'Invalid --set {bad} was accepted ({refused.returncode})')
        if config.read_text() != 'schema = broken\n': raise AssertionError(f'Refused --set {bad} still wrote the file')
    saved = cli('--set', 'tone_style=traditional', 'experimental_rewrite=true', 'webkit_compat=true')
    if saved.returncode != 0 or 'Đã lưu' not in saved.stdout:
        raise AssertionError(f'--set did not save: {saved.returncode} {saved.stdout!r} {saved.stderr!r}')
    data = tomllib.loads(config.read_text())
    if data['tone_style'] != 'traditional' or not data['experimental_rewrite'] or not data['webkit_compat']:
        raise AssertionError('--set choices did not reach the actual TOML data')
    journal = config.with_name('changes.log').read_text()
    if f'commit {data["generation"]}' not in journal: raise AssertionError('Saved settings lack their audit commit')
    again = cli('--show')
    if again.returncode != 0 or 'tone_style = "traditional"' not in again.stdout:
        raise AssertionError('Reopened settings lost the actual saved choices')
    # Settings apply at the next input-context change (documented in the --set message):
    # a real focus transition, password field and back, like leaving and re-entering a field.
    send('Tab'); pump(.15); send('Tab'); pump(.15)
    if word() != 'hòa': raise AssertionError('Settings CLI -> typing UI did not apply traditional tone placement')

    # Startup failure of the launched application: the NORMAL path posts a critical
    # notification. Captured on a PRIVATE bus; the desktop's own bus is never used.
    with tempfile.TemporaryDirectory(prefix='nr-', dir=ROOT / '.tmp') as runtime:
        bus = PrivateBus(runtime)
        sink = Sink(bus.address)
        try:
            failure_env = dict(child_env, XDG_RUNTIME_DIR=runtime, DBUS_SESSION_BUS_ADDRESS=bus.address)
            failure_env.pop('ZKEY_TEST_DISPLAY', None)  # exercise the NORMAL notification path
            result = subprocess.run([binary, '--run', '/zkey-test/nonexistent-application'], env=failure_env,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode != 1: raise AssertionError('Expected failed startup did not retain failure exit 1')
            if len(sink.calls) != 1: raise AssertionError(f'Expected one notification, got {sink.calls}')
            call = sink.calls[0]
            if 'Không khởi động được zkey native' not in call['body'] or call['urgency'] != 2 or call['timeout'] != 0:
                raise AssertionError(f'Startup failure notification is not critical/readable: {call}')
        finally:
            sink.close(); bus.close()
    print('PASS native settings: CLI error/recovery/validation; --set -> TOML + audit; --show; typing hoà -> hòa; '
          'startup failure = critical notification + exit 1')
