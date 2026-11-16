#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test-only framebuffer capture in a separate GTK3 process (also for GTK4)."""
import os
from pathlib import Path
import sys
if not os.environ.get('ZKEY_TEST_DISPLAY') or os.environ.get('DISPLAY') != os.environ['ZKEY_TEST_DISPLAY']:
    raise SystemExit('Capture requires the private test display')
root=Path(__file__).resolve().parents[2]
target=Path(sys.argv[1]).resolve()
if not target.is_relative_to(root/'.tmp'):
    raise SystemExit('Capture output must be under project scratch')
import gi
gi.require_version('Gdk','3.0')
from gi.repository import Gdk
Gdk.init([])
window=Gdk.get_default_root_window()
image=Gdk.pixbuf_get_from_window(window,0,0,window.get_width(),window.get_height())
if image is None:raise SystemExit('Private framebuffer capture unavailable')
image.savev(str(target),'png',[],[])
