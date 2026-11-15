#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Visible product application supervisor; logs its final status after closing."""
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def terminate(_signal, _frame):
    raise SystemExit(143)

signal.signal(signal.SIGTERM, terminate)
from zkey.launch import main
try:
    code = main()
except SystemExit as error:
    code = error.code
finally:
    print(f"GATE_EXIT={locals().get('code', 1)}", flush=True)
raise SystemExit(code)
