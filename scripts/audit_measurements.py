#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Triage obvious blind assertions; not proof of correctness or a replacement for review.

Scans tests and the protocol probe, never its own implementation. Exit 2 means
unmeasurable or suspicious candidates needing review, exit 0 means no listed shapes.
"""
import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def inspect(source):
    tree = ast.parse(source)
    assertions, findings = 0, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            assertions += 1
            if isinstance(node.test, ast.Constant):
                findings.append((node.lineno, "constant assertion"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.startswith("assert"):
            assertions += 1
            if node.func.attr in {"assertTrue", "assertFalse"} and node.args and isinstance(node.args[0], ast.Constant):
                findings.append((node.lineno, "constant unittest assertion"))
            if node.func.attr == "assertEqual" and len(node.args) >= 2:
                if ast.dump(node.args[0]) == ast.dump(node.args[1]):
                    findings.append((node.lineno, "same expression on both sides"))
        if isinstance(node, ast.ExceptHandler):
            if any(isinstance(item, ast.Pass) for item in node.body):
                findings.append((node.lineno, "exception silently ignored"))
            for item in node.body:
                if isinstance(item, ast.Return) and isinstance(item.value, (ast.List, ast.Dict, ast.Constant)):
                    if isinstance(item.value, ast.Constant) and type(item.value.value) is int and item.value.value != 0:
                        continue  # Explicit nonzero failure exit code, not a successful empty result.
                    findings.append((node.lineno, "exception converted to default value"))
    return assertions, findings


def main():
    paths = [Path(path) for path in sys.argv[1:]] if len(sys.argv) > 1 else [
        *sorted((ROOT / "tests").glob("test_*.py")), ROOT / "scripts/probe_ibus.py"]
    total, candidates = 0, 0
    if not paths:
        return 2
    for path in paths:
        try:
            count, findings = inspect(path.read_text())
        except (OSError, SyntaxError) as error:
            print(f"NOT_MEASURABLE {path}: {type(error).__name__}")
            return 2
        total += count
        for line, finding in findings:
            candidates += 1
            print(f"REVIEW {path}:{line}: {finding}")
    print(f"files={len(paths)}; assertions={total}; suspicious={candidates}; manual semantic review still required")
    return 2 if candidates or total == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
