#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Matrix of native acceptance lanes on a private Xvfb; one fresh Xvfb per lane (xvfb-run).
# Prints one line per lane with its GATE_EXIT; harm gate (desktop document portal) around ALL lanes.
# Usage: bash scripts/accept-native-matrix.sh            (all lanes)
#        ONLY=desktop-gtk3 bash scripts/accept-native-matrix.sh   (one lane, by name)
ROOT=/mnt/data/projects/zkey
export PATH="$ROOT/.tmp/tools/root/usr/bin:$PATH"
mount_pat=" /run/user/$(id -u)/doc "
before=$(grep -c -- "$mount_pat" /proc/mounts); portal_before=$(systemctl --user is-active xdg-document-portal.service 2>/dev/null)
lane() {  # name, script, env assignments...
  local name="$1" script="$2"; shift 2
  [ -n "${ONLY:-}" ] && [[ "$name" != $ONLY ]] && return 0
  # -u ZKEY_MODE: a parent shell's mode must never choose what a lane measures
  # (measured 20/11: ambient ZKEY_MODE=off made a shell-plugin lane measure plain typing).
  env -u WAYLAND_DISPLAY -u DISPLAY -u XAUTHORITY -u ZKEY_MODE "$@" \
    xvfb-run -a -f "$ROOT/.tmp/xvfb-matrix.auth" -s "-screen 0 1280x800x24 -nolisten tcp" \
    bash -c 'export ZKEY_TEST_DISPLAY="$DISPLAY"; cd '"$ROOT"' && /usr/bin/python3 '"$script" \
    > "$ROOT/.tmp/matrix-$name.log" 2>&1
  local code=$?
  echo "LANE $name exit=$code  $(grep -E '^PASS|FAILED|NOT_MEASURABLE' "$ROOT/.tmp/matrix-$name.log" | head -2 | cut -c1-200 | tr '\n' '|')"
}
lane launcher         native/tests/accept_launcher.py
lane launcher-vte     native/tests/accept_launcher.py  ZKEY_NATIVE_VTE=1
lane launcher-health  native/tests/accept_launcher.py  ZKEY_NATIVE_HEALTH_FAULT=1
lane desktop-gtk3     native/tests/accept_desktop.py
lane desktop-gtk4     native/tests/accept_desktop.py   ZKEY_NATIVE_GTK4=1
lane desktop-settings native/tests/accept_desktop.py   ZKEY_NATIVE_SETTINGS=1
# PRODUCTION path: the ibus-daemon starts `zkey-native --ibus` from a component XML.
lane component-gtk3   native/tests/accept_desktop.py   ZKEY_NATIVE_COMPONENT_MODE=1
lane component-gtk4   native/tests/accept_desktop.py   ZKEY_NATIVE_COMPONENT_MODE=1 ZKEY_NATIVE_GTK4=1
# N05 (toolkit level): key → GtkEntry text, xkb vs zkey, with a harness-injected slow arm.
lane latency          native/tests/accept_latency.py
after=$(grep -c -- "$mount_pat" /proc/mounts); portal_after=$(systemctl --user is-active xdg-document-portal.service 2>/dev/null)
echo "HARM_GATE portal $portal_before->$portal_after mount $before->$after"
echo "MATRIX_DONE"
