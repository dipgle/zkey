# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guard: no harness may start a private D-Bus with the real runtime dir.

15/11 20:37:45 the desktop's xdg-document-portal failed because
accept-ptyxis.py ran `dbus-run-session -- ptyxis` with XDG_RUNTIME_DIR real.
"""
from pathlib import Path
import os
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import private_bus  # noqa: E402

# A real launch: the program as a list element / shell command, not prose.
LAUNCH = re.compile(r"""["']dbus-run-session["']|^\s*(?:exec\s+)?dbus-run-session\b""", re.M)
ALLOWED = {"scripts/private_bus.py", "zkey/launch.py"}


def violations(files):
    found = []
    for path, text in files:
        if path in ALLOWED:
            continue
        for match in LAUNCH.finditer(text):
            found.append(f"{path}:{text.count(chr(10), 0, match.start()) + 1}")
    return found


def sources():
    for pattern in ("scripts/*.py", "scripts/*.sh", "zkey/*.py", "bin/*"):
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                yield path.relative_to(ROOT).as_posix(), path.read_text(errors="replace")


class PrivateBusTests(unittest.TestCase):
    def test_bus_socket_is_in_the_private_runtime_not_snap_hidden_tmp(self):
        import xml.etree.ElementTree as ET
        argv, env = private_bus.command(['true'], {'XDG_RUNTIME_DIR': '/run/user/1000'})
        options = [part for part in argv if part.startswith('--config-file=')]
        self.assertEqual(len(options), 1, 'default /tmp D-Bus socket is invisible inside snap')
        config = Path(options[0].split('=', 1)[1])
        runtime = Path(env['XDG_RUNTIME_DIR'])
        self.assertTrue(config.is_relative_to(runtime))
        tree = ET.parse(config)
        self.assertEqual([item.text for item in tree.findall('listen')], [f'unix:path={runtime}/bus'])
        self.assertEqual([item.text for item in tree.findall('auth')], ['EXTERNAL'])
        for item in tree.findall('includedir'):
            self.assertTrue(Path(item.text).is_absolute(), 'moving config must not move policy directories')

    def test_no_harness_launches_dbus_run_session_itself(self):
        self.assertEqual(violations(sources()), [])

    def test_scanner_catches_the_15_11_shape_and_ignores_prose(self):
        bad = 'launcher = subprocess.Popen(["dbus-run-session", "--", "ptyxis"], env=env)\n'
        shell = 'set -u\ndbus-run-session -- env A=1 python3 x.py\n'
        prose = '"""Run under dbus-run-session."""\nprint("use dbus-run-session with X")\n'
        self.assertEqual(violations([("scripts/x.py", bad)]), ["scripts/x.py:1"])
        self.assertEqual(violations([("scripts/x.sh", shell)]), ["scripts/x.sh:2"])
        self.assertEqual(violations([("scripts/y.py", prose)]), [])

    def test_product_launcher_gives_its_bus_a_scratch_runtime(self):
        text = (ROOT / "zkey/launch.py").read_text()
        self.assertIn('XDG_RUNTIME_DIR=str(scratch / "runtime")', text)
        self.assertLess(text.index('XDG_RUNTIME_DIR=str(scratch / "runtime")'), text.index('"dbus-run-session"'))

    def test_helper_bus_never_sees_the_real_runtime_dir(self):
        argv, env = private_bus.command(["true"], {"XDG_RUNTIME_DIR": "/run/user/1000", "WAYLAND_DISPLAY": "wayland-0"})
        runtime = Path(env["XDG_RUNTIME_DIR"])
        self.assertEqual(argv[0], "dbus-run-session")
        self.assertEqual(argv[2], "--")
        self.assertTrue(runtime.is_relative_to(ROOT / ".tmp"))
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)
        self.assertEqual(env["ZKEY_REAL_RUNTIME_DIR"], "/run/user/1000")
        self.assertNotIn("WAYLAND_DISPLAY", env)


if __name__ == "__main__":
    unittest.main()
