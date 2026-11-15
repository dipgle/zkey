import unittest
from scripts.impact import extract, select


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.graph = {"nodes": ["a", "b", "test1", "test2"],
                      "edges": [["a", "b"], ["b", "test1"]], "tests": ["test1", "test2"]}

    def test_transitive_and_negative_control(self):
        selected, affected, full = select(self.graph, ["a"])
        self.assertEqual(selected, {"test1"})
        self.assertEqual(affected, {"a", "b", "test1"})
        self.assertFalse(full)
        # Damaging the graph must not produce a falsely empty/green selection.
        self.graph["edges"] = []
        self.assertEqual(select(self.graph, ["a"])[0], {"test1", "test2"})
        self.assertTrue(select(self.graph, ["a"])[2])

    def test_unknown_node_runs_full_and_cycles_terminate(self):
        self.assertTrue(select(self.graph, ["new-file"])[2])
        self.graph["edges"].append(["b", "a"])
        self.assertEqual(select(self.graph, ["a"])[0], {"test1"})

    def test_extracted_native_loader_reaches_session_tests(self):
        graph = extract()
        selected, _, full = select(graph, ["src/telex.rs"])
        self.assertFalse(full)
        self.assertTrue(any("test_word_then_boundary" in test for test in selected))
        self.assertTrue(any(test.startswith("cargo::") for test in selected))


if __name__ == "__main__":
    unittest.main()
