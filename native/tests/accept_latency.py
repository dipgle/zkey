#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Latency A/B on a PRIVATE Xvfb: how long from a synthetic key to text committed by the widget.

N05 asks for an honest "typing feels fast" number. Three arms on the same display and the same
real GTK3 Entry, one key per measurement:

  xkb   — the plain `xkb:us::eng` engine (baseline: no Vietnamese composition engine)
  zkey  — the native zkey engine over a private IBus (the product path)
  slow  — the zkey arm with a deliberate +12 ms delay injected by THIS harness after the clock
          starts and before the key goes out; an arm that cannot separate this is blind.

What is measured: key press → GtkEntry `changed` signal, i.e. engine round-trip plus toolkit
commit. This is NOT pixel-level (N05 stays open for keys→pixels; a first attempt sampling the X
framebuffer with XGetImage was discarded because the Entry caret blinks inside the sampled cell
and produced false "changed" readings even with a 200 ms injected delay — recorded in
docs/verification.md). Only synthetic keys ('m', a consonant Telex never rewrites).

Exit 0 measured, within budget, and the control arm detected; 1 budget/control failure;
2 not measurable (no private display / no attested binary). Ends GATE_EXIT.
"""
from pathlib import Path
import ctypes as C
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import private_bus

BINARY = ROOT / 'native/target/release/zkey-native'
SAMPLES = int(os.environ.get('ZKEY_LATENCY_SAMPLES', '25'))
SLOW_MS = float(os.environ.get('ZKEY_LATENCY_SLOW_MS', '12'))
BUDGET_P95_MS = float(os.environ.get('ZKEY_LATENCY_BUDGET_P95_MS', '40'))


def x11():
    x = C.CDLL('libX11.so.6')
    t = C.CDLL('libXtst.so.6')
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
    x.XDefaultRootWindow.argtypes, x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
    x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
    x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
    x.XFlush.argtypes = [C.c_void_p]
    x.XSync.argtypes = [C.c_void_p, C.c_int]
    x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
    t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
    return x, t


def inside():
    import gi
    from provenance import verify
    try:
        verify(BINARY)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f'native binary does not attest current source: {error}') from error

    x, t = x11()
    display = x.XOpenDisplay(os.environ['DISPLAY'].encode())
    if not display:
        raise RuntimeError('private X display unavailable')
    keycode = x.XKeysymToKeycode(display, x.XStringToKeysym(b'm'))
    if not keycode:
        raise RuntimeError('keycode for m unavailable')

    def run_arm(name, delay_ms):
        gi.require_version('Gtk', '3.0')
        from gi.repository import GLib, Gtk
        main = GLib.MainContext.default()

        def pump():
            for _ in range(500):
                if not main.pending():
                    break
                main.iteration(False)

        entry = Gtk.Entry()
        entry.set_width_chars(40)
        window = Gtk.Window(title=f'zkey latency — {name} (synthetic)')
        window.add(entry)
        window.show_all()
        window.present()
        entry.grab_focus()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not window.get_window():
            pump()
            time.sleep(0.01)
        pump()
        # No window manager here: put X keyboard focus on the toplevel the way one would.
        x.XSetInputFocus(display, window.get_window().get_xid(), 1, 0)
        x.XSync(display, False)
        pump()

        stamps = []
        entry.connect('changed', lambda _e: stamps.append(time.perf_counter()))

        def send_key():
            t.XTestFakeKeyEvent(display, keycode, True, 0)
            t.XTestFakeKeyEvent(display, keycode, False, 0)
            x.XFlush(display)

        # One untimed key proves the widget receives keys at all before anything is timed.
        send_key()
        warm = time.monotonic() + 1.0
        while time.monotonic() < warm and not entry.get_text():
            pump()
            time.sleep(0.002)
        if not entry.get_text():
            window.destroy()
            raise RuntimeError(f'{name}: a synthetic key never reached the Entry (no focus?)')

        values = []
        for index in range(SAMPLES + 1):
            entry.set_text('')          # clears via the model, so 'changed' fires outside the window
            pump()
            stamps.clear()
            while main.pending():
                main.iteration(False)
            stamps.clear()
            started = time.perf_counter()
            if delay_ms:
                # Control arm only: the delay sits between the clock and the key, so a working
                # measurement must report it.
                time.sleep(delay_ms / 1000)
            send_key()
            until = started + 2.0
            while not stamps and time.perf_counter() < until:
                pump()
            if not stamps:
                window.destroy()
                raise AssertionError(f'{name}: no text committed within 2 s of a key')
            if index:                   # sample 0 is warm-up (fresh IM context)
                values.append((stamps[0] - started) * 1000)
            time.sleep(0.02)
        window.destroy()
        pump()
        return values

    with tempfile.TemporaryDirectory(prefix='latency-', dir=ROOT / '.tmp') as temporary:
        scratch = Path(temporary)
        for name in ('config', 'cache', 'data'):
            (scratch / name).mkdir(mode=0o700)
        env = dict(os.environ, IBUS_ADDRESS=f'unix:path={scratch}/ibus.sock',
                   IBUS_ADDRESS_FILE=str(scratch / 'address'), GTK_IM_MODULE='ibus',
                   IBUS_ENABLE_SYNC_MODE='1', ZKEY_NATIVE_READY=str(scratch / 'ready'),
                   ZKEY_NATIVE_TRACE='1',
                   XDG_CONFIG_HOME=str(scratch / 'config'), XDG_CACHE_HOME=str(scratch / 'cache'),
                   XDG_DATA_HOME=str(scratch / 'data'), GSETTINGS_BACKEND='memory',
                   ZKEY_NATIVE_CONFIG_PATH=str(scratch / 'preferences.toml'))
        env.pop('IBUS_USE_PORTAL', None)
        os.environ.update(env)
        log = (ROOT / '.tmp/latency-engine.log').open('w')
        children = []
        try:
            daemon = subprocess.Popen(['ibus-daemon', '--single', '--panel=disable', '--config=disable',
                                       '--emoji-extension=disable', '--cache=none',
                                       f'--address={env["IBUS_ADDRESS"]}'],
                                      env=env, stdout=log, stderr=log, start_new_session=True)
            children.append(daemon)
            until = time.monotonic() + 8
            while not (scratch / 'ibus.sock').exists():
                if daemon.poll() is not None or time.monotonic() > until:
                    raise RuntimeError('private IBus did not start')
                time.sleep(0.01)
            engine = subprocess.Popen([str(BINARY), '--engine', '--experimental-rewrite'], env=env,
                                      stdout=log, stderr=log, start_new_session=True)
            children.append(engine)
            while not (scratch / 'ready').exists():
                if engine.poll() is not None or time.monotonic() > until:
                    raise RuntimeError('native engine did not register')
                time.sleep(0.01)
            gi.require_version('IBus', '1.0')
            from gi.repository import IBus
            IBus.init()
            bus = IBus.Bus.new()

            def arm(engine_name, delay_ms=0.0):
                if not bus.set_global_engine(engine_name):
                    raise RuntimeError(f'cannot select engine {engine_name}')
                time.sleep(0.4)  # engine switch is applied on the next focus
                return run_arm(engine_name, delay_ms)

            control = arm('xkb:us::eng')
            product = arm('zkey-native')
            slow = arm('zkey-native', SLOW_MS)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)

    log.flush()
    trace = (ROOT / '.tmp/latency-engine.log').read_text(errors='replace')
    seen = trace.count('zkey-native: key-event')
    if seen < SAMPLES:
        print(f'WRONG ENGINE: the native engine saw {seen} key events, expected ≥ {SAMPLES} '
              '⇒ the numbers do not describe zkey')
        return 1

    def summary(values):
        ordered = sorted(values)
        return {'n': len(values), 'p50': statistics.median(ordered),
                'p95': ordered[max(0, int(len(ordered) * 0.95) - 1)], 'max': ordered[-1]}

    rows = {'xkb': summary(control), 'zkey': summary(product), 'slow': summary(slow)}
    print('LATENCY ms (key → GtkEntry text committed; private Xvfb; toolkit-level, NOT pixels)')
    for name, row in rows.items():
        print(f'  {name:5s} n={row["n"]:3d} p50={row["p50"]:7.2f} p95={row["p95"]:7.2f} max={row["max"]:7.2f}')
    print(f'  overhead zkey-xkb p50={rows["zkey"]["p50"] - rows["xkb"]["p50"]:+.2f} '
          f'p95={rows["zkey"]["p95"] - rows["xkb"]["p95"]:+.2f}')
    if rows['slow']['p50'] < rows['zkey']['p50'] + SLOW_MS * 0.5:
        print(f'CONTROL FAILED: the injected +{SLOW_MS:g} ms arm was not detected '
              f'(slow p50 {rows["slow"]["p50"]:.2f} vs zkey {rows["zkey"]["p50"]:.2f}) ⇒ measurement blind')
        return 1
    if rows['zkey']['p95'] > BUDGET_P95_MS:
        print(f'BUDGET FAILED: zkey p95 {rows["zkey"]["p95"]:.2f} ms > {BUDGET_P95_MS:g} ms')
        return 1
    print(f'PASS latency: zkey p95 {rows["zkey"]["p95"]:.2f} ms ≤ {BUDGET_P95_MS:g} ms; '
          f'control arm +{SLOW_MS:g} ms detected (the gate can go red)')
    return 0


def main():
    if sys.argv[1:] == ['--inside']:
        try:
            return inside()
        except AssertionError as error:
            print(f'LATENCY FAILED: {error}')
            return 1
        except (OSError, RuntimeError, ValueError) as error:
            print(f'NOT_MEASURABLE: {error}')
            return 2
    display = os.environ.get('ZKEY_TEST_DISPLAY')
    if not display:
        print('NOT_MEASURABLE: requires PRIVATE ZKEY_TEST_DISPLAY')
        return 2
    if not BINARY.is_file():
        print('NOT_MEASURABLE: build native/target/release/zkey-native first')
        return 2
    env = dict(os.environ, DISPLAY=display, GDK_BACKEND='x11', GIO_USE_VFS='local', NO_AT_BRIDGE='1')
    env.pop('IBUS_USE_PORTAL', None)
    env.pop('ZKEY_NATIVE_SESSION_ROOT', None)
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), '--inside'], env)


if __name__ == '__main__':
    result = main()
    print(f'GATE_EXIT={result}', flush=True)
    raise SystemExit(result)
