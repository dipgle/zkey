#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Isolated protocol probe only; does not restart or select the desktop's IBus.
set -u
ROOT="/mnt/data/projects/zkey"
cd "$ROOT" || exit 2
mkdir -p "$ROOT/.tmp"
dbus-run-session -- env ZKEY_ISOLATED_BUS=1 GIO_USE_VFS=local NO_AT_BRIDGE=1 /usr/bin/python3 "$ROOT/scripts/probe_ibus.py" > "$ROOT/.tmp/ibus-probe.log" 2>&1
code=$?
printf '\nGATE_EXIT=%s\n' "$code" >> "$ROOT/.tmp/ibus-probe.log"
exit "$code"
