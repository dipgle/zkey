#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Close only the empty test fixture via its Close button, then test fresh runtime."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
from editor_ui import connect, walk, document

ROOT = Path(__file__).resolve().parents[1]
pid = json.loads((ROOT / ".tmp/editor-app.json").read_text())["pid"]
Atspi, editor = document(pid)
if Atspi.Text.get_text(editor.get_text_iface(), 0, -1).strip():
    raise RuntimeError("Test document is no longer empty; refusing to close it")
Atspi, app = connect(pid)
closed = False
for node in walk(app):
    if node.get_name() == "Close" and node.get_role() == Atspi.Role.PUSH_BUTTON:
        action = node.get_action_iface()
        if action is not None and Atspi.Action.get_n_actions(action) > 0:
            closed = Atspi.Action.do_action(action, 0)
            break
if not closed:
    raise RuntimeError("The test window's Close button could not be activated")
until = time.monotonic() + 8
while Path(f"/proc/{pid}").exists() and time.monotonic() < until:
    time.sleep(0.05)
if Path(f"/proc/{pid}").exists():
    raise RuntimeError("Old test editor did not exit; not opening a duplicate")
env = os.environ.copy()
env.pop("AT_SPI_BUS_ADDRESS", None)
env["ZKEY_TRACE"] = "1"  # Metadata only; never key values or input text.
subprocess.run([sys.executable, str(ROOT / "scripts/open-editor-host.py")], env=env, check=True)
raise SystemExit(subprocess.call([sys.executable, str(ROOT / "scripts/accept-editor.py")]))
