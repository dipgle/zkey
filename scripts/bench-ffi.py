#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Measure Python -> our Rust FFI only, not IBus/application/display latency.

Uses the same words/prefix schedule as src/bin/bench.rs for comparison.
No content from keyboard, clipboard, documents or user configuration is read.
"""
from pathlib import Path
import argparse
import json
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zkey.core import Core  # noqa: E402


def measure(samples):
    if samples < 100:
        raise ValueError('At least 100 samples are required for percentile reporting')
    core = Core()
    words = ('dduwowngf', 'tieengs', 'nguyeenx', 'NGUYEENX', 'thuwowngr')
    for word in words:
        for _ in range(1000):
            core.compose(word)
    delays = []
    for i in range(samples):
        word = words[i % len(words)]
        prefix = word[:1 + i % len(word)]
        before = perf_counter_ns()
        core.compose(prefix)
        delays.append(perf_counter_ns() - before)
    delays.sort()
    return dict(scope='Python UTF-8 + ctypes + Rust replay; excludes IBus, application, compositor',
                samples=samples, p50_ns=delays[samples // 2], p95_ns=delays[samples * 95 // 100],
                p99_ns=delays[samples * 99 // 100], max_ns=delays[-1])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=100_000)
    args = parser.parse_args()
    try:
        print(json.dumps(measure(args.samples)))
    except (OSError, ValueError) as error:
        print(f'NOT_MEASURABLE: {error}', file=sys.stderr)
        raise SystemExit(2)
