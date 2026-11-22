#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Acceptance of the INSTALLED native engine (no user display, no input-source change):
#   1. Firefox's measured D-Bus call pattern against the running engine.
#   2. A real GTK3 Entry on a private Xvfb through the running engine.
# Each gate carries its own reverse control; both must be red when the engine
# stops composing. Exit 0 all pass, 1 red, 2 not measurable.
set -u
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PY=/usr/bin/python3
code=0

run() {  # label expected-exit command...
  local label=$1 expected=$2; shift 2
  "$@" > "$ROOT/.tmp/accept-installed-$label.log" 2>&1
  local got=$?
  tail -n 3 "$ROOT/.tmp/accept-installed-$label.log" | sed "s/^/[$label] /"
  if [ "$got" != "$expected" ]; then
    echo "FAIL $label: expected exit $expected, got $got"
    [ "$got" = 2 ] && code=2 || { [ "$code" = 0 ] && code=1; }
  fi
}

run firefox-pattern        0  "$PY" "$ROOT/native/tests/accept_firefox_pattern.py"
run firefox-control        1  env ZKEY_FIREFOX_SKIP_SURROUNDING=1 "$PY" "$ROOT/native/tests/accept_firefox_pattern.py"
run silent-context         0  "$PY" "$ROOT/native/tests/accept_silent_context.py"
run gtk3-entry             0  "$PY" "$ROOT/native/tests/accept_installed_gtk3.py"
run gtk3-control           0  env ZKEY_INSTALLED_SKIP_ENGINE=1 "$PY" "$ROOT/native/tests/accept_installed_gtk3.py"

echo "GATE_EXIT=$code"
exit "$code"
