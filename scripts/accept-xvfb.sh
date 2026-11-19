#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Real-key acceptance on a PRIVATE Xvfb display: GNOME Text Editor (GTK4) +
# GTK3 burst/password. Keys are XTest events into that display only, never the
# user's desktop; no RemoteDesktop portal consent. Private D-Bus + IBus.
# Output: .tmp/accept-xvfb.log ending with GATE_EXIT (0 pass, 1 fail, 2 not measurable).
set -u
ROOT=/mnt/data/projects/zkey
LOG="$ROOT/.tmp/accept-xvfb.log"
mkdir -p "$ROOT/.tmp"
# Project-local Xvfb (apt-get download + dpkg-deb -x; no system install).
export PATH="$ROOT/.tmp/tools/root/usr/bin:$PATH"
if [ "${1:-}" != "--inner" ]; then
  if ! command -v Xvfb >/dev/null || ! command -v xvfb-run >/dev/null; then
    printf 'NOT_MEASURABLE: Xvfb/xvfb-run not installed\nGATE_EXIT=2\n' | tee "$LOG"
    exit 2
  fi
  # Harm gate: these tests must leave the RUNNING desktop as it was. Measured
  # case 15/11 20:37:45: a private bus took over /run/user/UID/doc and the
  # desktop's xdg-document-portal failed. Compare before/after.
  doc_mount=" /run/user/$(id -u)/doc "
  doc_before=$(grep -c -- "$doc_mount" /proc/mounts)
  portal_before=$(systemctl --user is-active xdg-document-portal.service 2>/dev/null)
  env -u WAYLAND_DISPLAY -u DISPLAY -u XAUTHORITY \
    xvfb-run -a -f "$ROOT/.tmp/xvfb.auth" -s "-screen 0 1280x800x24 -nolisten tcp" \
    bash "$0" --inner > "$LOG" 2>&1
  code=$?
  doc_after=$(grep -c -- "$doc_mount" /proc/mounts)
  portal_after=$(systemctl --user is-active xdg-document-portal.service 2>/dev/null)
  if [ "$doc_before" -ge 1 ] && { [ "$doc_after" -lt "$doc_before" ] || [ "$portal_after" != "$portal_before" ]; }; then
    printf '\nẢNH HƯỞNG MÁY: desktop document portal %s->%s, mount %s->%s\n' \
      "$portal_before" "$portal_after" "$doc_before" "$doc_after" >> "$LOG"
    code=1
  elif [ "$doc_before" -lt 1 ]; then
    printf '\nKHÔNG ĐO ĐƯỢC tác động lên máy: desktop chưa có mount %s trước khi chạy (portal %s)\n' \
      "$doc_mount" "$portal_before" >> "$LOG"
    [ "$code" = 0 ] && code=2
  else
    printf '\nMÁY NGUYÊN: desktop document portal %s, mount %s->%s\n' "$portal_after" "$doc_before" "$doc_after" >> "$LOG"
  fi
  printf '\nGATE_EXIT=%s\n' "$code" >> "$LOG"
  cat "$LOG"
  exit "$code"
fi

# --- inside xvfb-run: DISPLAY/XAUTHORITY point at the private server ---
cd "$ROOT" || exit 2
# Ambients must not choose the plugin mode under test (measured 19/11:
# a parent shell with ZKEY_MODE=off made the VTE plugin lane measure nothing).
unset ZKEY_MODE
export ZKEY_TEST_DISPLAY="$DISPLAY" ZKEY_CLIENT_GDK_BACKEND=x11 ZKEY_TRACE=1
export ZKEY_APP_PID_FILE="$ROOT/.tmp/xvfb-editor-app.json"
unset WAYLAND_DISPLAY IBUS_USE_PORTAL
[ -e "$ZKEY_APP_PID_FILE" ] && : > "$ZKEY_APP_PID_FILE"
echo "display=$DISPLAY"
setsid /usr/bin/python3 -m zkey.launch > "$ROOT/.tmp/xvfb-editor-session.log" 2>&1 &
launcher=$!
pid=""
for _ in $(seq 1 200); do
  if [ -s "$ZKEY_APP_PID_FILE" ]; then
    pid=$(/usr/bin/python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["pid"])' "$ZKEY_APP_PID_FILE")
    [ -e "/proc/$pid" ] && break
  fi
  kill -0 "$launcher" 2>/dev/null || break
  sleep 0.1
done
if [ -z "$pid" ] || [ ! -e "/proc/$pid" ]; then
  echo "EDITOR FAILED TO START; see .tmp/xvfb-editor-session.log"
  kill -TERM -- "-$launcher" 2>/dev/null
  exit 1
fi
echo "editor_pid=$pid"
# The editor's private IBus socket names its engine trace: .tmp/run-XXXX/ibus.sock -> .tmp/run-XXXX.log
engine_log=$(tr '\0' '\n' < "/proc/$pid/environ" | sed -n 's#^IBUS_ADDRESS=unix:path=\(.*\)/ibus.sock$#\1#p' | xargs -r basename)
sleep 2  # let the toplevel map and AT-SPI register
/usr/bin/python3 "$ROOT/scripts/accept-editor.py"
code=$?
echo "accept-editor exit=$code"
grep -v '^dbus-daemon' "$ROOT/.tmp/native-acceptance.log"
if [ -n "$engine_log" ] && [ -e "$ROOT/.tmp/$engine_log.log" ]; then
  seen=$(grep -c 'key-state' "$ROOT/.tmp/$engine_log.log")
  echo "editor engine key-state=$seen ($engine_log.log)"
  # Correct text without our engine seeing the keys proves nothing about zkey.
  if [ "$seen" -lt 7 ]; then echo "WRONG ENGINE: private zkey saw $seen key calls"; code=1; fi
else
  echo "editor engine trace: NOT FOUND"
  [ "$code" = 0 ] && code=2
fi
kill -TERM -- "-$launcher" 2>/dev/null
wait "$launcher" 2>/dev/null
# Real VTE terminal: input-method bypass alone, then with the bash plugin.
for plugin in 0 1; do
  ZKEY_TERMINAL_PLUGIN=$plugin /usr/bin/python3 "$ROOT/scripts/accept-terminal.py" 2>&1 | grep -v '^dbus-daemon'
  term=${PIPESTATUS[0]}
  echo "terminal plugin=$plugin exit=$term"
  if [ "$term" != 0 ] && [ "$code" != 1 ]; then code=$term; fi
done
# The real ptyxis app with the user's own ~/.bashrc (installed plugin).
if grep -q -x -F '# >>> zkey shell plugin >>>' "$HOME/.bashrc" 2>/dev/null; then
  /usr/bin/python3 "$ROOT/scripts/accept-ptyxis.py"
  pty=$?
else
  echo "NOT_MEASURABLE: ~/.bashrc has no zkey block (bash scripts/install-shell.sh)"
  pty=2
fi
echo "ptyxis exit=$pty"
if [ "$pty" != 0 ] && [ "$code" != 1 ]; then code=$pty; fi
# Settings screen -> typing app, across roles (private config file).
/usr/bin/python3 "$ROOT/scripts/accept-settings.py" 2>&1 | grep -vE '^dbus-daemon|SpiRegistry'
settings=${PIPESTATUS[0]}
echo "settings exit=$settings"
if [ "$settings" != 0 ] && [ "$code" != 1 ]; then code=$settings; fi
# Bash plugin vs machine-typed commands (private tmux server, no X needed).
bash "$ROOT/scripts/accept-shell-tmux.sh"
shell=$?
echo "shell-tmux exit=$shell"
if [ "$shell" != 0 ] && [ "$code" != 1 ]; then code=$shell; fi
exit "$code"
