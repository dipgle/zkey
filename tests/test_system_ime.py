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
# Byte copy of the real ~/.config/environment.d/95-fcitx5.conf (16/11).
FCITX_ENV_FULL = ("GTK_IM_MODULE=fcitx\nQT_IM_MODULE=fcitx\nQT_IM_MODULES=fcitx\n"
                  "XMODIFIERS=@im=fcitx\nSDL_IM_MODULE=fcitx\n")
FCITX_AUTOSTART = ("[Desktop Entry]\nName=Fcitx 5\nExec=/usr/bin/fcitx5 -d\nType=Application\n"
                   "X-GNOME-Autostart-enabled=true\n")


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
        # Never read the host's /etc/xdg autostart entries from a unit test.
        self.env = patch.dict("os.environ", {"HOME": str(self.home), "ZKEY_SKIP_GSETTINGS": "1",
                                             "XDG_CONFIG_DIRS": str(self.home / "no-system")})
        self.env.start()
        # Never ask the host's real ibus-daemon from a unit test; tests that care override this.
        engines = patch.object(system_ime, "engine_names", create=True, return_value={"xkb:us::eng", "zkey"})
        engines.start()
        self.addCleanup(engines.stop)

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def test_enable_writes_ibus_session_with_sync_mode_and_component(self):
        code, _ = run("enable")
        self.assertEqual(code, 0)
        text = (self.home / ".config/environment.d/99-zkey.conf").read_text()
        self.assertIn("IBUS_ENABLE_SYNC_MODE=1\n", text)
        self.assertIn("GTK_IM_MODULE=ibus\n", text)
        # 95-fcitx5.conf also sets the plural Qt list (preferred by Qt >= 6.7)
        # and SDL; leaving them makes those apps start/use fcitx5 (16/11).
        for key in ("QT_IM_MODULE", "QT_IM_MODULES", "SDL_IM_MODULE", "XMODIFIERS"):
            fcitx_keys = {line.split("=")[0] for line in FCITX_ENV_FULL.splitlines()}
            self.assertIn(key, fcitx_keys)
            self.assertRegex(text, rf"(?m)^{key}=(ibus|@im=ibus)$")
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

    # 16/11 measured on the real login: a user autostart fcitx5 claimed
    # org.freedesktop.IBus first, GNOME's ibus-daemon failed ("current session
    # already has an ibus-daemon") and zkey never received a key.
    def test_user_fcitx5_autostart_is_hidden_then_restored_byte_for_byte(self):
        autostart = self.home / ".config/autostart/org.fcitx.Fcitx5.desktop"
        autostart.parent.mkdir(parents=True)
        autostart.write_text(FCITX_AUTOSTART)
        with patch.dict("os.environ", {"XDG_CONFIG_DIRS": str(self.home / "no-system")}):
            self.assertEqual(run("enable")[0], 0)
            text = autostart.read_text()
            self.assertIn("\nHidden=true\n", text)
            self.assertIn("Exec=/usr/bin/fcitx5 -d", text, "keeps the entry, only hides it")
            self.assertEqual(run("disable")[0], 0)
        self.assertEqual(autostart.read_text(), FCITX_AUTOSTART)

    def test_system_fcitx5_autostart_gets_a_user_override_removed_on_disable(self):
        system = self.home / "etc-xdg"
        (system / "autostart").mkdir(parents=True)
        (system / "autostart/org.fcitx.Fcitx5.desktop").write_text(FCITX_AUTOSTART)
        override = self.home / ".config/autostart/org.fcitx.Fcitx5.desktop"
        with patch.dict("os.environ", {"XDG_CONFIG_DIRS": str(system)}):
            self.assertEqual(run("enable")[0], 0)
            self.assertIn("\nHidden=true\n", override.read_text())
            self.assertEqual(run("disable")[0], 0)
        self.assertFalse(override.exists())
        self.assertFalse((self.home / ".config/autostart").exists())
        self.assertEqual((system / "autostart/org.fcitx.Fcitx5.desktop").read_text(), FCITX_AUTOSTART)

    def test_unrelated_or_already_hidden_autostart_is_left_alone(self):
        autostart = self.home / ".config/autostart"
        autostart.mkdir(parents=True)
        (autostart / "other.desktop").write_text("[Desktop Entry]\nType=Application\nExec=/usr/bin/foo\n")
        hidden = FCITX_AUTOSTART + "Hidden=true\n"
        (autostart / "org.fcitx.Fcitx5.desktop").write_text(hidden)
        with patch.dict("os.environ", {"XDG_CONFIG_DIRS": str(self.home / "no-system")}):
            self.assertEqual(run("enable")[0], 0)
            self.assertEqual((autostart / "org.fcitx.Fcitx5.desktop").read_text(), hidden)
            self.assertNotIn("Hidden", (autostart / "other.desktop").read_text())
            self.assertEqual(run("disable")[0], 0)
        self.assertEqual((autostart / "org.fcitx.Fcitx5.desktop").read_text(), hidden)

    def test_verify_names_the_ibus_owner_and_is_red_for_fcitx5(self):
        for owner, want in (("ibus-daemon", 0), ("fcitx5", 1), (None, 2)):
            with patch.object(system_ime, "ibus_owner", return_value=owner):
                code, output = run("verify")
            self.assertEqual(code, want, (owner, output))
            if owner:
                self.assertIn(owner, output)

    def test_verify_is_red_while_the_lingering_user_manager_keeps_the_old_environment(self):
        # 16/11 23:59 measured: Linger=yes keeps systemd --user (and its
        # environment) alive across log out, so it still had QT_IM_MODULES=fcitx
        # even though 99-zkey.conf said ibus: logging out alone fixes nothing.
        env_file = self.home / ".config/environment.d/99-zkey.conf"
        env_file.write_text(system_ime.env_text(self.home / ".local"))
        fresh = dict(line.split("=", 1) for line in env_file.read_text().splitlines()
                     if "=" in line and not line.startswith("#"))
        stale = {**fresh, "QT_IM_MODULES": "fcitx", "SDL_IM_MODULE": "fcitx"}
        for manager, want in ((fresh, 0), (stale, 1), (None, 2)):
            with (patch.object(system_ime, "ibus_owner", return_value="ibus-daemon"),
                  patch.object(system_ime, "manager_env", return_value=manager)):
                code, output = run("verify")
            self.assertEqual(code, want, (manager, output))
            if want == 1:
                self.assertIn("QT_IM_MODULES", output)
                self.assertIn("SDL_IM_MODULE", output)
                self.assertIn("reboot", output)
        # Stale environment is reported even while fcitx5 still owns the name.
        with (patch.object(system_ime, "ibus_owner", return_value="fcitx5"),
              patch.object(system_ime, "manager_env", return_value=stale)):
            code, output = run("verify")
        self.assertEqual(code, 1)
        self.assertIn("QT_IM_MODULES", output)

    def test_verify_is_red_when_the_running_daemon_has_no_zkey_engine(self):
        # 18/11 20:55 measured after the reboot: ibus-daemon owned the name and the
        # environment was right, yet `ibus list-engine` had 1261 engines and NO zkey
        # (registry cache dated 12/11 never recorded ~/.local/share/ibus/component),
        # so the input source ('ibus','zkey') pointed at nothing. Owner/env alone
        # said OK; the daemon must also know the engine.
        for engines, want in (({"xkb:us::eng", "zkey"}, 0), ({"xkb:us::eng"}, 1), (None, 2)):
            with (patch.object(system_ime, "ibus_owner", return_value="ibus-daemon"),
                  patch.object(system_ime, "engine_names", return_value=engines)):
                code, output = run("verify")
            self.assertEqual(code, want, (engines, output))
            if want == 1:
                self.assertIn("zkey", output)
                self.assertIn("registry", output)

    def test_parse_engine_names_reads_ibus_list_engine_output(self):
        text = "language: Hawaiian\n  xkb:us:haw:haw - Hawaiian\nlanguage: Vietnamese\n  zkey - zkey\n"
        self.assertEqual(system_ime.parse_engine_names(text), {"xkb:us:haw:haw", "zkey"})
        self.assertEqual(system_ime.parse_engine_names("Can't connect to IBus.\n"), set())


if __name__ == "__main__":
    unittest.main()
