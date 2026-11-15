#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Probe: does `zkey --run ptyxis` stay alive? Run INSIDE a private Xvfb
# (xvfb-run ... bash scripts/probe-run-ptyxis.sh [rounds]). Each round starts
# the launcher, waits HOLD seconds, records whether ptyxis is still alive and
# keeps that round's launcher log. Control: same with GTK's simple IM (no IBus).
# Exit 0 = measured (counts printed), 2 = not measurable.
set -u
ROOT=/mnt/data/projects/zkey
ROUNDS=${1:-6}
HOLD=${HOLD:-12}
OUT="$ROOT/.tmp/probe-run-ptyxis"
mkdir -p "$OUT"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "NOT_MEASURABLE: needs a private X display only"; exit 2; }
command -v ptyxis >/dev/null || { echo "NOT_MEASURABLE: ptyxis missing"; exit 2; }
for mode in ibus simple; do
  alive=0
  for r in $(seq 1 "$ROUNDS"); do
    log="$OUT/$mode-$r.log"
    extra=()
    [ "$mode" = simple ] && extra=(ZKEY_CLIENT_IM_MODULE=gtk-im-context-simple)
    env "${extra[@]}" ZKEY_CLIENT_GDK_BACKEND=x11 ZKEY_TRACE=1 \
      setsid "$ROOT/bin/zkey" --run ptyxis --standalone > "$log" 2>&1 &
    launcher=$!
    pid=""
    for _ in $(seq 1 50); do
      pid=$(pgrep -s "$launcher" -x ptyxis | head -1)
      [ -n "$pid" ] && break
      sleep 0.2
    done
    sleep "$HOLD"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then state=alive; alive=$((alive + 1)); else state=dead; fi
    code=""
    kill -0 "$launcher" 2>/dev/null || { wait "$launcher"; code=$?; }
    echo "$mode round $r: ptyxis=${pid:-never-started} $state launcher_exit=${code:-running}" | tee -a "$log"
    kill -TERM -- "-$launcher" 2>/dev/null
    wait "$launcher" 2>/dev/null
    sleep 1
  done
  echo "RESULT $mode: alive $alive/$ROUNDS after ${HOLD}s"
done
exit 0
