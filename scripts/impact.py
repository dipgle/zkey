#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extract import/module dependencies, augment with actual unittest call traces.

Unknown or unobserved input selects ALL tests. No hand-authored application graph.
--record runs tests and writes docs/dependencies.json only after success.
"""
import argparse
import ast
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAP = ROOT / "docs/dependencies.json"


def extract(root=ROOT):
    nodes, edges, tests = set(), set(), set()
    for folder, extension in (("zkey", "*.py"), ("scripts", "*.py"), ("tests", "*.py"), ("src", "*.rs"),
                              ("native/src", "*.rs"), ("native/tests", "*.py"), ("native/tests", "*.rs"),
                              ("native/tools", "*.py"), ("native", "build.rs")):
        for path in (root / folder).rglob(extension):
            name = path.relative_to(root).as_posix()
            nodes.add(name)
            source = path.read_text()
            if path.suffix == ".rs":
                crate_src = "native/src" if name.startswith("native/") else "src"
                for module in re.findall(r"^\s*(?:pub\s+)?mod (\w+);", source, re.M):
                    candidate=path.parent / (module + ".rs")
                    if candidate.is_file():
                        dependency=candidate.relative_to(root).as_posix()
                        nodes.add(dependency)
                        edges.add((dependency, name))
                for module in re.findall(r"\bcrate::(\w+)::",source):
                    dependency=f"{crate_src}/{module}.rs"
                    if (root/dependency).is_file():
                        nodes.add(dependency)
                        edges.add((dependency,name))
                for included in re.findall(r'include_str!\("([^"\n]+)"\)',source):
                    dependency=(path.parent/included).relative_to(root).as_posix()
                    nodes.add(dependency)
                    edges.add((dependency,name))
                if "use zkey_core::" in source:
                    edges.add(("src/lib.rs", name))
                if "use zkey_native::" in source:
                    edges.add(("native/src/lib.rs",name))
                for test in re.findall(r"#\[test\]\s*fn (\w+)", source):
                    test_id = f"cargo::{name}::{test}"
                    nodes.add(test_id)
                    tests.add(test_id)
                    edges.add((name, test_id))
                continue
            tree = ast.parse(source)
            for item in ast.walk(tree):
                if isinstance(item, ast.ImportFrom) and item.module:
                    prefix = path.parent.relative_to(root).parts if item.level else ()
                    if item.level > 1:
                        prefix = prefix[:1 - item.level]
                    candidate = "/".join((*prefix, *item.module.split("."))) + ".py"
                    if (root / candidate).is_file():
                        nodes.add(candidate)
                        edges.add((candidate, name))
                if isinstance(item, ast.ClassDef) and folder in ("tests","native/tests"):
                    for method in item.body:
                        if isinstance(method, ast.FunctionDef) and method.name.startswith("test_"):
                            prefix="native.tests." if folder=="native/tests" else ""
                            test_id = f"test::{prefix}{path.stem}.{item.name}.{method.name}"
                            nodes.add(test_id)
                            tests.add(test_id)
                            edges.add((name, test_id))
            # The FFI artifact name is present in the actual loader's source.
            if folder == "zkey" and '"target/release/libzkey_core.so"' in source and "ctypes.CDLL(" in source:
                edges.add(("src/lib.rs", name))
            if folder=="native/tests" and path.name.startswith("accept_"):
                test_id=f"e2e::{name}"
                nodes.add(test_id);tests.add(test_id)
                edges.add((name,test_id))
            if "native/target/release/zkey-native" in source:
                edges.add(("native/src/main.rs",name))
    nodes.update({"Cargo.toml", "Cargo.lock", "native/Cargo.toml", "native/Cargo.lock", "native/build.rs"})
    for name in tuple(nodes):
        if name.startswith("src/"):
            edges.add(("Cargo.toml", name))
            edges.add(("Cargo.lock", name))
        elif name.startswith("native/src/"):
            edges.add(("native/Cargo.toml",name))
            edges.add(("native/Cargo.lock",name))
            edges.add(("native/build.rs",name))
    return {"nodes": sorted(nodes), "edges": sorted([list(edge) for edge in edges]), "tests": sorted(tests)}


def select(graph, changed):
    all_tests = set(graph["tests"])
    known = set(graph["nodes"])
    if not changed or any(path not in known for path in changed):
        return all_tests, known, True
    affected = set(changed)
    while True:
        new = {target for source, target in graph["edges"] if source in affected}
        if new <= affected:
            break
        affected.update(new)
    selected = affected & all_tests
    if not selected:
        return all_tests, known, True
    return selected, affected, False


class TraceResult(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test)
        self.current_id = "test::" + test.id()
        self.observed = set()
        self.previous = sys.gettrace()
        sys.settrace(self.trace)

    def trace(self, frame, event, arg):
        if event == "call":
            try:
                path = Path(frame.f_code.co_filename).resolve().relative_to(ROOT).as_posix()
                if path.startswith(("zkey/", "scripts/", "tests/", "native/")):
                    self.observed.add(path)
            except ValueError:
                pass
        return self.trace

    def stopTest(self, test):
        sys.settrace(self.previous)
        self.trace_edges.update((path, self.current_id) for path in self.observed)
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--changed", nargs="*")
    args = parser.parse_args()
    graph = extract()
    if args.record:
        TraceResult.trace_edges = set()
        suite = unittest.TestSuite([
            unittest.defaultTestLoader.discover(str(ROOT / "tests")),
            unittest.defaultTestLoader.loadTestsFromName("native.tests.test_stage"),
        ])
        result = unittest.TextTestRunner(verbosity=1, resultclass=TraceResult).run(suite)
        if not result.wasSuccessful() or result.testsRun == 0:
            return 1
        graph["edges"] = sorted([list(edge) for edge in set(map(tuple, graph["edges"])) | TraceResult.trace_edges])
        graph["trace"] = {"command": "/usr/bin/python3 scripts/impact.py --record", "python_tests_run": result.testsRun}
        MAP.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n")
    elif MAP.exists():
        recorded = json.loads(MAP.read_text())
        # Retain observed edges only between nodes still present in freshly extracted source.
        known = set(graph["nodes"])
        graph["edges"] = sorted([list(edge) for edge in set(map(tuple, graph["edges"])) | {
            tuple(edge) for edge in recorded["edges"] if set(edge) <= known}])
    selected, affected, full = select(graph, args.changed)
    print(f"changed={args.changed}; affected={len(affected)} nodes; run={len(selected)}/{len(graph['tests'])} tests; full={full}")
    for test in sorted(selected):
        print(test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
