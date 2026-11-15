# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import shlex
import tempfile
import unittest
import xml.etree.ElementTree as ET
from scripts.stage import ROOT, stage


class StageTests(unittest.TestCase):
    def test_component_and_launcher_agree_on_prefix_with_spaces(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            output = stage(Path(temporary) / "stage", Path(temporary) / "user prefix")
            component = ET.parse(output).getroot()
            command = shlex.split(component.findtext("exec"))
            self.assertEqual(command, [str(Path(temporary) / "user prefix/bin/zkey"), "--ibus"])
            self.assertEqual(component.findtext("engines/engine/name"), "zkey")
            self.assertTrue((Path(temporary) / "stage/lib/zkey/target/release/libzkey_core.so").is_file())
            launcher = Path(temporary) / "stage/bin/zkey"
            self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
            compile(launcher.read_text(), str(launcher), "exec")

    def test_stage_rejects_outside_destination(self):
        with self.assertRaises(ValueError):
            stage(Path.home() / ".local", Path.home() / ".local")


if __name__ == "__main__":
    unittest.main()
