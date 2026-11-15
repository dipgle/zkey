#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One host verification run; read the actual exit statuses of both scripts."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
results = {name: subprocess.call(["bash", str(ROOT / "scripts" / name)], cwd=ROOT)
           for name in ("probe-host.sh", "desktop-host.sh")}
print(results, flush=True)
status = 1 if any(value != 0 for value in results.values()) else 0
print(f"GATE_EXIT={status}", flush=True)
raise SystemExit(status)
