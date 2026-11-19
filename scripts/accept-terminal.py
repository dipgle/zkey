#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real XTest keys into a real VTE terminal widget (bash), private IBus + display.

P0-001 safety half: a terminal must get keys unchanged and a password typed
with ECHO off must neither appear on screen nor be transformed. Only synthetic
one-time strings; the secret is compared inside the shell, never printed.
Run under xvfb-run via scripts/accept-xvfb.sh-style wrapper (ZKEY_TEST_DISPLAY).
"""
from pathlib import Path
import ctypes as C
import os
import subprocess
import sys
import time
from x11_activation import activate, is_active

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402  (never dbus-run-session directly)
sys.path.insert(0, str(ROOT))
FAKE_SECRET = "as"  # One-time test string; Telex would turn it into "á".
# Reverse control for this gate only (never product behaviour): "compare" makes
# the shell expect the Telex form, "echo" types the secret with ECHO on. Both
# must turn this gate RED.
MUTATE = os.environ.get("ZKEY_TERMINAL_MUTATE", "")
# 1 = bash sources shell/zkey.bash: Telex done by readline on the command line.
# "home" = the user's own ~/.bashrc as installed by scripts/install-shell.sh.
PLUGIN_MODE = os.environ.get("ZKEY_TERMINAL_PLUGIN", "0")
PLUGIN = PLUGIN_MODE in ("1", "home")
# The gate pins the plugin mode instead of inheriting an ambient ZKEY_MODE
# (measured 19/11: a shell with ZKEY_MODE=off made the gate measure nothing).
# Counter-check: ZKEY_MODE_UNDER_TEST=off must turn this gate RED.
TEST_MODE = os.environ.get("ZKEY_MODE_UNDER_TEST", "quoted")


def inside():
    from zkey.runtime import isolated_engine
    with isolated_engine() as (env, _bus, _children):
        os.environ.update(env)
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkX11", "3.0")
        gi.require_version("Vte", "2.91")
        from gi.repository import GdkX11, GLib, Gtk, Vte
        if not Gtk.init_check([])[0]:
            print("NOT_MEASURABLE: cannot open X11 display")
            return 2
        window = Gtk.Window(title="zkey — kiểm terminal (dữ liệu giả)")
        window.set_default_size(720, 300)
        terminal = Vte.Terminal()
        window.add(terminal)
        errors = []
        handlers = [GLib.log_set_handler(domain, GLib.LogLevelFlags.LEVEL_WARNING | GLib.LogLevelFlags.LEVEL_CRITICAL,
                                         lambda _d, _l, message, _u: errors.append(message), None)
                    for domain in ("Gtk", "Gdk", "IBUS", "VTE")]
        shell_env = [f"{k}={v}" for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TERM")]
        shell_env += [f"ZKEY_MODE={TEST_MODE}", "PS1=$ ", "HISTFILE=/dev/null", "LANG=C.UTF-8"]
        spawned = []
        shell = {"1": ["/bin/bash", "--rcfile", str(ROOT / "shell/zkey.bash"), "-i"],
                 "home": ["/bin/bash", "-i"]}.get(PLUGIN_MODE, ["/bin/bash", "--norc", "--noprofile", "-i"])
        terminal.spawn_async(Vte.PtyFlags.DEFAULT, str(ROOT / ".tmp"), shell,
                             shell_env, GLib.SpawnFlags.DEFAULT, None, None, -1, None,
                             lambda _t, pid, error, *_: spawned.append((pid, error)))
        window.show_all()
        context = GLib.MainContext.default()

        def pump(seconds=0.08):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                while context.pending():
                    context.iteration(False)
                time.sleep(0.002)

        def screen():
            text = terminal.get_text_format(Vte.Format.TEXT)
            return text or ""

        def wait_for(predicate, what, seconds=4):
            until = time.monotonic() + seconds
            while not predicate() and time.monotonic() < until:
                pump(0.02)
            if not predicate():
                raise AssertionError(f"Terminal did not show {what}")

        wait_for(lambda: spawned, "a spawned shell")
        if spawned[0][1] is not None:
            raise RuntimeError(f"Shell spawn failed: {spawned[0][1]}")
        wait_for(lambda: screen().rstrip().endswith("$"), "the shell prompt")
        xid = GdkX11.X11Window.get_xid(window.get_window())
        x11 = C.CDLL("libX11.so.6")
        xtest = C.CDLL("libXtst.so.6")
        x11.XOpenDisplay.argtypes, x11.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        x11.XStringToKeysym.argtypes, x11.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        x11.XKeysymToKeycode.argtypes, x11.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_uint
        x11.XFlush.argtypes = [C.c_void_p]
        x11.XCloseDisplay.argtypes = [C.c_void_p]
        xtest.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        display = x11.XOpenDisplay(os.environ["DISPLAY"].encode())
        if not display:
            raise RuntimeError("XTest display unavailable")
        try:
            activate(x11, display, xid, lambda: pump(0.02))
            terminal.grab_focus()
            pump(0.3)
            names = {" ": "space", "-": "minus", "$": "dollar", "=": "equal", '"': "quotedbl",
                     "[": "bracketleft", "]": "bracketright", "'": "apostrophe", "\\": "backslash", "&": "ampersand", "|": "bar", ";": "semicolon"}

            def send(text):
                for char in text:
                    if not is_active(x11, display, xid):
                        raise RuntimeError("Focus left the test terminal; stopped before injecting a key")
                    name = "Return" if char == "\n" else names.get(char, char)
                    keysym = x11.XStringToKeysym(name.encode())
                    code = x11.XKeysymToKeycode(display, keysym)
                    if not code:
                        raise RuntimeError(f"Test key unavailable: {name}")
                    shift = char in '$"&|' or char.isupper()
                    shift_code = x11.XKeysymToKeycode(display, x11.XStringToKeysym(b"Shift_L"))
                    if shift:
                        xtest.XTestFakeKeyEvent(display, shift_code, True, 0)
                    xtest.XTestFakeKeyEvent(display, code, True, 0)
                    xtest.XTestFakeKeyEvent(display, code, False, 0)
                    if shift:
                        xtest.XTestFakeKeyEvent(display, shift_code, False, 0)
                    x11.XFlush(display)
                    pump(0.03)

            # 1. Ordinary command line: keys reach the shell unchanged (bypass).
            send("echo tieengs\n")
            wait_for(lambda: "\ntieengs" in screen(), "the echoed command output")
            # 2. ECHO-off secret prompt: nothing visible, nothing transformed.
            before = screen()
            # "compare": the Telex form of the secret, typed as ASCII escapes.
            # Unquoted literal: the shell plugin (quoted mode) leaves it as typed.
            expected = "$'\\xc3\\xa1'" if MUTATE == "compare" else FAKE_SECRET
            flag = "" if MUTATE == "echo" else "-s "
            command = "read " + flag + '-r p; [ "$p" = ' + expected + ' ] && echo SAME || echo DIFF; unset p\n'
            send(command)
            pump(0.4)
            send(FAKE_SECRET)
            pump(0.4)
            during = screen()
            if during.count(FAKE_SECRET) != before.count(FAKE_SECRET) + command.count(FAKE_SECRET) or "á" in during:
                # Allowed occurrences: only those inside the typed command line itself.
                raise AssertionError("Secret keys became visible on screen while ECHO was off")
            send("\n")
            wait_for(lambda: "SAME" in screen().split("unset p", 1)[-1] or "DIFF" in screen().split("unset p", 1)[-1],
                     "the shell's comparison result")
            if "DIFF" in screen().split("unset p", 1)[-1]:
                raise AssertionError("Secret typed with ECHO off reached the shell transformed")
            if PLUGIN:
                def prompt_line():
                    lines = [line for line in screen().splitlines() if line.strip()]
                    return lines[-1] if lines else ""
                # 3. Per key inside quotes: the command line shows each prefix at once.
                send('echo "')
                for key, text in zip("tieengs", ("t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng")):
                    send(key)
                    wait_for(lambda: prompt_line().endswith('echo "' + text), f"prefix {text!r} on the command line")
                send(' vieetj"\n')
                wait_for(lambda: "\ntiếng việt" in screen(), "the Vietnamese phrase echoed by bash")
                # 4. Outside quotes commands/English stay as typed.
                send("echo status test\n")
                wait_for(lambda: "\nstatus test" in screen(), "unquoted English kept as typed")
                if "statú" in screen() or "tét" in screen():
                    raise AssertionError("Unquoted English was transformed")
            engine_log = ROOT / ".tmp" / (Path(env["IBUS_ADDRESS"].split("unix:path=", 1)[1]).parent.name + ".log")
            trace = engine_log.read_text()
            if "purpose=10" not in trace or "protected=True" not in trace:
                raise AssertionError("Private zkey never saw the terminal declare purpose TERMINAL")
            keys = trace.count("key-state ")
            if keys < 20:
                raise AssertionError(f"Wrong input engine: private zkey observed only {keys} key calls")
            if errors:
                raise RuntimeError("Toolkit warnings: " + "; ".join(errors))
            print(f"PASS VTE terminal: command keys unchanged; ECHO-off secret not shown and reached shell unchanged; "
                  f"engine saw purpose TERMINAL and {keys} keys; 0 toolkit warnings.")
            if PLUGIN:
                print("PASS shell plugin: 7 per-key prefixes inside quotes on the real command line; "
                      "'tiếng việt' reached bash; unquoted 'status test' kept as typed.")
                print("NOT COVERED: ptyxis app, SSH/tmux, vim/TUI, zsh.")
            else:
                print("NOT COVERED: Vietnamese typing inside terminals (bypassed), ptyxis app, SSH/tmux, raw/TUI.")
            return 0
        finally:
            x11.XCloseDisplay(display)
            window.destroy()
            for domain, handler in zip(("Gtk", "Gdk", "IBUS", "VTE"), handlers):
                GLib.log_remove_handler(domain, handler)


def main():
    if sys.argv[1:] == ["--inside"]:
        try:
            return inside()
        except (OSError, RuntimeError, AssertionError) as error:
            print(f"TERMINAL FAILED: {error}", file=sys.stderr)
            return 1
    if not os.environ.get("ZKEY_TEST_DISPLAY"):
        print("NOT_MEASURABLE: run inside a private Xvfb (ZKEY_TEST_DISPLAY unset)")
        return 2
    env = os.environ.copy()
    env["DISPLAY"] = env["ZKEY_TEST_DISPLAY"]
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("IBUS_USE_PORTAL", None)
    env.update(ZKEY_ISOLATED_BUS="1", GTK_IM_MODULE="ibus", GDK_BACKEND="x11", NO_AT_BRIDGE="1",
               GIO_USE_VFS="local", ZKEY_TRACE="1")
    return private_bus.call([sys.executable, str(Path(__file__).resolve()), "--inside"], env)


if __name__ == "__main__":
    status = main()
    print(f"GATE_EXIT={status}", flush=True)
    raise SystemExit(status)
