# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from zkey.config import Config, config_path, load, record_change, save

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=ROOT / ".tmp")
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / "config.toml"

    def test_missing_uses_defaults_and_write_round_trip(self):
        self.assertEqual(load(self.path), Config())
        expected = Config(enabled=False, modern_tone=False, max_word_keys=64)
        save(expected, self.path)
        self.assertEqual(load(self.path), expected)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_change_log_records_only_changed_keys_with_time_and_user(self):
        when = datetime(2026, 11, 15, 21, 0, tzinfo=timezone(timedelta(hours=7)))
        with patch.dict("os.environ", {"USER": "tester"}):
            line = record_change(Config(), Config(modern_tone=False), self.path, now=when)
            self.assertIsNone(record_change(Config(), Config(), self.path, now=when))
        self.assertEqual(line, "2026-11-15T21:00:00+07:00 tester modern_tone=true->false")
        self.assertEqual((self.path.parent / "changes.log").read_text(), line + "\n")

    def test_bad_data_is_not_silently_defaulted(self):
        for data in ('enabled = "yes"', 'max_word_keys = 0', 'max_word_keys = true',
                     'modren_tone = true', 'enabled = [', 'max_word_keys = 257'):
            self.path.write_text(data)
            with self.assertRaises(ValueError, msg=data):
                load(self.path)

    def test_explicit_preferences_survive_application_xdg_isolation(self):
        with patch.dict("os.environ", {"ZKEY_CONFIG_PATH": str(self.path), "XDG_CONFIG_HOME": str(self.path.parent / "isolated")}):
            expected = Config(modern_tone=False)
            save(expected)
            self.assertEqual(config_path(), self.path)
            self.assertEqual(load(), expected)


if __name__ == "__main__":
    unittest.main()
