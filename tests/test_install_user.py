# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import contextlib
import importlib.util
import io
import os
import shlex
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install_user", ROOT / "scripts/install-user.py")
install_user = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install_user)


def quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as output:
        code = function(*args, **kwargs)
    return code, output.getvalue()


class InstallUserTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / ".tmp")
        self.prefix = Path(self.temporary.name) / "my prefix"
        self.prefix.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_install_ships_launcher_plugin_line_binary_and_desktop_entry(self):
        code, _ = quiet(install_user.install, self.prefix)
        self.assertEqual(code, 0)
        for relative in ("bin/zkey", "lib/zkey/zkey/engine.py", "lib/zkey/target/release/libzkey_core.so",
                         "lib/zkey/target/release/zkey-line", "lib/zkey/shell/zkey.bash", "lib/zkey/LICENSE",
                         "share/applications/zkey.desktop"):
            self.assertTrue((self.prefix / relative).is_file(), relative)
        self.assertTrue(os.access(self.prefix / "bin/zkey", os.X_OK))
        self.assertTrue(os.access(self.prefix / "lib/zkey/target/release/zkey-line", os.X_OK))
        self.assertFalse((self.prefix / "share/ibus/component/zkey.xml").exists(), "system IME path is opt-in")
        exec_line = next(l for l in (self.prefix / "share/applications/zkey.desktop").read_text().splitlines()
                         if l.startswith("Exec="))
        # Desktop Entry quoting is double-quote based; shlex reads it the same here.
        self.assertEqual(shlex.split(exec_line[5:]), [str(self.prefix.resolve() / "bin/zkey"), "--run"])
        manifest = install_user.read_manifest(self.prefix.resolve())
        self.assertIn("bin/zkey", manifest)

    def test_refuses_to_overwrite_a_file_it_did_not_install(self):
        foreign = self.prefix / "bin/zkey"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("someone else's tool\n")
        code, output = quiet(install_user.install, self.prefix)
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", output)
        self.assertEqual(foreign.read_text(), "someone else's tool\n")
        self.assertFalse((self.prefix / "lib/zkey").exists())

    def test_reinstall_is_idempotent(self):
        self.assertEqual(quiet(install_user.install, self.prefix)[0], 0)
        self.assertEqual(quiet(install_user.install, self.prefix)[0], 0)

    def test_uninstall_removes_only_its_own_untouched_files(self):
        neighbour = self.prefix / "share/applications/other.desktop"
        neighbour.parent.mkdir(parents=True)
        neighbour.write_text("[Desktop Entry]\n")
        self.assertEqual(quiet(install_user.install, self.prefix)[0], 0)
        # What a run leaves behind (engine log, bytecode) is removed too.
        (self.prefix / "lib/zkey/.tmp").mkdir()
        (self.prefix / "lib/zkey/.tmp/run-x.log").write_text("key-state\n")
        (self.prefix / "lib/zkey/zkey/__pycache__").mkdir()
        code, _ = quiet(install_user.uninstall, self.prefix)
        self.assertEqual(code, 0)
        self.assertFalse((self.prefix / "bin/zkey").exists())
        self.assertFalse((self.prefix / "lib/zkey").exists())
        self.assertTrue(neighbour.is_file(), "a neighbour file must survive uninstall")

    def test_uninstall_keeps_an_edited_file_and_says_so(self):
        self.assertEqual(quiet(install_user.install, self.prefix)[0], 0)
        edited = self.prefix / "lib/zkey/shell/zkey.bash"
        edited.write_text(edited.read_text() + "# user tweak\n")
        code, output = quiet(install_user.uninstall, self.prefix)
        self.assertEqual(code, 1)
        self.assertIn("KEPT", output)
        self.assertTrue(edited.is_file())
        self.assertFalse((self.prefix / "bin/zkey").exists())


if __name__ == "__main__":
    unittest.main()
