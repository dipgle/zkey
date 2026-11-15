# SPDX-License-Identifier: AGPL-3.0-or-later
import unittest
from scripts.audit_measurements import inspect


class AuditTests(unittest.TestCase):
    def test_broken_assertions_are_flagged_then_repaired_are_clear(self):
        for broken in ("assert True", "self.assertTrue(True)", "self.assertEqual(value, value)",
                       "try:\n work()\nexcept Exception:\n pass"):
            self.assertGreater(len(inspect(broken)[1]), 0, broken)
        for valid in ("assert value == expected", "self.assertEqual(actual, expected)",
                      "self.assertFalse(result.handled)",
                      "try:\n work()\nexcept Exception:\n return 1"):
            self.assertEqual(inspect(valid)[1], [], valid)


if __name__ == "__main__":
    unittest.main()
