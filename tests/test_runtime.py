# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import os
import tempfile
import unittest
from zkey.runtime import ROOT, prune_logs


class RuntimeTests(unittest.TestCase):
    def test_prune_keeps_newest_logs_and_never_touches_run_directories(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            directory = Path(temporary)
            for index in range(7):
                log = directory / f"run-{index}.log"
                log.write_text("key-state\n")
                os.utime(log, (1000 + index, 1000 + index))
            live = directory / "run-live"
            live.mkdir()
            removed = prune_logs(directory, keep=3)
            self.assertEqual(removed, 4)
            self.assertEqual(sorted(p.name for p in directory.glob("run-*.log")),
                             ["run-4.log", "run-5.log", "run-6.log"])
            self.assertTrue(live.is_dir())

    def test_prune_with_fewer_logs_removes_nothing(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary:
            (Path(temporary) / "run-a.log").write_text("")
            self.assertEqual(prune_logs(temporary, keep=3), 0)
            self.assertTrue((Path(temporary) / "run-a.log").exists())


if __name__ == "__main__":
    unittest.main()
