"""Entrypoints must compile; AST parsing alone misses duplicate lambda arguments."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EntrypointTests(unittest.TestCase):
    def test_all_python_entrypoints_compile(self):
        paths = sorted((ROOT / "zkey").glob("*.py")) + sorted((ROOT / "scripts").glob("*.py")) + [ROOT / "bin/zkey"]
        self.assertGreater(len(paths), 1)
        for path in paths:
            with self.subTest(path=path.name):
                compile(path.read_text(), str(path), "exec")
