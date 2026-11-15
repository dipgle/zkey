# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import contextlib
import importlib.util
import io
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("system_ime", ROOT / "scripts/system-ime.py")
system_ime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(system_ime)
XINPUTRC = "# im-config(8) generated\nrun_im fcitx5\n# im-config signature: x  -\n"
FCITX = "GTK_IM_MODULE=fcitx\nQT_IM_MODULE=fcitx\nXMODIFIERS=@im=fcitx\n"


def run(action):
    with contextlib.redirect_stdout(io.StringIO()) as output:
        code = getattr(system_ime, action)()
    return code, output.getvalue()


class SystemImeTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / ".tmp")
        self.home = Path(self.temporary.name)
        (self.home / ".xinputrc").write_text(XINPUTRC)
        (self.home / ".config/environment.d").mkdir(parents=True)
        (self.home / ".config/environment.d/95-fcitx5.conf").write_text(FCITX)
        self.env = patch.dict("os.environ", {"HOME": str(self.home), "ZKEY_SKIP_GSETTINGS": "1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def test_enable_writes_ibus_session_with_sync_mode_and_component(self):
        code, _ = run("enable")
        self.assertEqual(code, 0)
        text = (self.home / ".config/environment.d/99-zkey.conf").read_text()
        self.assertIn("IBUS_ENABLE_SYNC_MODE=1\n", text)
        self.assertIn("GTK_IM_MODULE=ibus\n", text)
        self.assertIn(f"{self.home / '.local'}/share/ibus/component", text)
        self.assertGreater("99-zkey.conf", "95-fcitx5.conf", "must sort after fcitx5 to win")
        self.assertIn("run_im ibus", (self.home / ".xinputrc").read_text())
        self.assertTrue((self.home / ".local/share/ibus/component/zkey.xml").is_file())

    def test_disable_restores_every_original_byte_for_byte(self):
        self.assertEqual(run("enable")[0], 0)
        code, _ = run("disable")
        self.assertEqual(code, 0)
        self.assertEqual((self.home / ".xinputrc").read_text(), XINPUTRC)
        self.assertEqual(sorted(p.name for p in (self.home / ".config/environment.d").iterdir()), ["95-fcitx5.conf"])
        self.assertEqual((self.home / ".config/environment.d/95-fcitx5.conf").read_text(), FCITX)
        self.assertFalse((self.home / ".local/share/ibus/component/zkey.xml").exists())
        self.assertFalse((self.home / ".local/state/zkey").exists())

    def test_disable_removes_xinputrc_that_did_not_exist(self):
        (self.home / ".xinputrc").unlink()
        self.assertEqual(run("enable")[0], 0)
        self.assertEqual(run("disable")[0], 0)
        self.assertFalse((self.home / ".xinputrc").exists())

    def test_refuses_twice_and_refuses_a_foreign_99_file(self):
        self.assertEqual(run("enable")[0], 0)
        code, output = run("enable")
        self.assertEqual(code, 1)
        self.assertIn("already enabled", output)
        self.assertEqual(run("disable")[0], 0)
        foreign = self.home / ".config/environment.d/99-zkey.conf"
        foreign.write_text("MINE=1\n")
        code, output = run("enable")
        self.assertEqual(code, 1)
        self.assertEqual(foreign.read_text(), "MINE=1\n")
        self.assertEqual((self.home / ".xinputrc").read_text(), XINPUTRC)

    def test_gnome_input_source_added_then_restored_on_a_private_keyfile_backend(self):
        # Real gsettings, but stored in this fake HOME (never the user's dconf).
        import subprocess
        env = {"GSETTINGS_BACKEND": "keyfile", "XDG_CONFIG_HOME": str(self.home / ".config"),
               "ZKEY_SKIP_GSETTINGS": "0"}
        with patch.dict("os.environ", env):
            get = lambda: subprocess.run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
                                         capture_output=True, text=True, check=True).stdout.strip()
            subprocess.run(["gsettings", "set", "org.gnome.desktop.input-sources", "sources", "[('xkb', 'us')]"],
                           check=True)
            self.assertTrue((self.home / ".config/glib-2.0/settings/keyfile").is_file(), "private keyfile in use")
            self.assertEqual(run("enable")[0], 0)
            self.assertEqual(get(), "[('xkb', 'us'), ('ibus', 'zkey')]")
            self.assertEqual(run("disable")[0], 0)
            self.assertEqual(get(), "[('xkb', 'us')]")

    def test_disable_without_enable_changes_nothing(self):
        code, output = run("disable")
        self.assertEqual(code, 1)
        self.assertEqual((self.home / ".xinputrc").read_text(), XINPUTRC)


if __name__ == "__main__":
    unittest.main()
