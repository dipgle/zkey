#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Open a standalone Text Editor with private zkey; no system input changes."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
marker = ROOT / ".tmp/editor-app.json"
env = os.environ.copy()
desktop = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True)
if desktop.returncode:
    print("NOT_MEASURABLE: desktop environment unavailable")
    raise SystemExit(2)
for line in desktop.stdout.splitlines():
    key, separator, value = line.partition("=")
    if separator and key in {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR"}:
        env[key] = value
env.pop("GDK_BACKEND", None)
env.update(ZKEY_APP_PID_FILE=str(marker), ZKEY_CLIENT_GDK_BACKEND="x11", GIO_USE_VFS="local", NO_AT_BRIDGE="1")
marker.unlink(missing_ok=True)
with (ROOT / ".tmp/editor-session.log").open("w") as log:
    supervisor = subprocess.Popen([sys.executable, str(ROOT / "scripts/editor-session.py")],
        env=env, cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
(ROOT / ".tmp/editor-supervisor.pid").write_text(str(supervisor.pid) + "\n")
deadline = time.monotonic() + 10
while not marker.exists():
    if supervisor.poll() is not None or time.monotonic() > deadline:
        print("OPEN FAILED: read .tmp/editor-session.log")
        raise SystemExit(1)
    time.sleep(0.02)
application = json.loads(marker.read_text())
os.kill(application["pid"], 0)
print(f"APP_STARTED pid={application['pid']} supervisor={supervisor.pid}; window visibility must be checked separately.")
print("Log .tmp/editor-session.log receives GATE_EXIT when the user closes the editor.")
