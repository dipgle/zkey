#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# N05 (partial): key → GtkEntry text-committed latency, zkey vs xkb on a PRIVATE Xvfb.
# Toolkit-level, NOT pixels; not a desktop A/B. Harm gate: the running desktop must be untouched.
# Env: ZKEY_LATENCY_SAMPLES (25), ZKEY_LATENCY_SLOW_MS (12), ZKEY_LATENCY_BUDGET_P95_MS (40).
# Output: .tmp/accept-latency.log ending with GATE_EXIT (0 pass, 1 fail/control blind, 2 not measurable).
set -u
ROOT=/mnt/data/projects/zkey
LOG="$ROOT/.tmp/accept-latency.log"
mkdir -p "$ROOT/.tmp"
export PATH="$ROOT/.tmp/tools/root/usr/bin:$PATH"
if ! command -v Xvfb >/dev/null || ! command -v xvfb-run >/dev/null; then
  printf 'NOT_MEASURABLE: Xvfb/xvfb-run not installed\nGATE_EXIT=2\n' | tee "$LOG"
  exit 2
fi
mount_pat=" /run/user/$(id -u)/doc "
before=$(grep -c -- "$mount_pat" /proc/mounts); portal_before=$(systemctl --user is-active xdg-document-portal.service 2>/dev/null)
# ZKEY_MODE in the caller's shell must not choose anything under test (measured 20/11: ambient
# ZKEY_MODE=off made a shell-plugin lane measure plain typing).
env -u WAYLAND_DISPLAY -u DISPLAY -u XAUTHORITY -u ZKEY_MODE \
  xvfb-run -a -f "$ROOT/.tmp/xvfb.auth" -s "-screen 0 1280x800x24 -nolisten tcp" \
  bash -c 'export ZKEY_TEST_DISPLAY="$DISPLAY"; cd '"$ROOT"' && /usr/bin/python3 native/tests/accept_latency.py' \
  > "$LOG" 2>&1
code=$?
after=$(grep -c -- "$mount_pat" /proc/mounts); portal_after=$(systemctl --user is-active xdg-document-portal.service 2>/dev/null)
if [ "$before" -ge 1 ] && { [ "$after" -lt "$before" ] || [ "$portal_after" != "$portal_before" ]; }; then
  printf 'ẢNH HƯỞNG MÁY: portal %s->%s mount %s->%s\n' "$portal_before" "$portal_after" "$before" "$after" >> "$LOG"
  code=1
else
  printf 'MÁY NGUYÊN: portal %s, mount %s->%s\n' "$portal_after" "$before" "$after" >> "$LOG"
fi
grep -vE '^dbus-daemon|SpiRegistry' "$LOG" | tail -12
echo "GATE_EXIT=$code" | tee -a "$LOG"
exit "$code"
