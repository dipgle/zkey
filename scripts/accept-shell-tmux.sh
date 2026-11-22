#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Bash plugin (shell/zkey.bash) on a real interactive bash + readline inside a
# PRIVATE tmux server (-L, never the user's/huba's server). Synthetic text only.
#
#  M  machine-typed command (tmux send-keys -l, the way huba/launchers type):
#     must reach bash verbatim. Regression lock for 15/11: quoted mode turned
#     `project_doc_max_bytes` -> `mã`, `PROJECTS_ROOT` -> `RÔT`,
#     `Bash(git reset:*)` -> `git rết` (broke codex, weakened --disallowedTools).
#  I  identifiers / ALL-CAPS typed at human speed: verbatim.
#  H  Vietnamese typed at human speed inside quotes: composed (reverse control —
#     a plugin that never composes would pass M and I but fails here).
# Exit: 0 pass, 1 fail, 2 not measurable. Ends with GATE_EXIT.
set -u
ROOT=/mnt/data/projects/zkey
OUT=$(mktemp -d "$ROOT/.tmp/shell-tmux.XXXXXX")
SOCK=zkey-accept-$$
T() { tmux -L "$SOCK" "$@"; }
finish() { T kill-server 2>/dev/null; rm -rf "$OUT"; echo "GATE_EXIT=$1"; exit "$1"; }
command -v tmux >/dev/null || { echo "NOT_MEASURABLE: tmux missing"; finish 2; }
if [ ! -x "$ROOT/native/target/release/zkey-native" ] && [ ! -x "$ROOT/target/release/zkey-line" ]; then
  echo "NOT_MEASURABLE: zkey-native (native/target/release) not built"; finish 2
fi

PLUGIN=${ZKEY_PLUGIN:-$ROOT/shell/zkey.bash}  # counter-checks pass a broken copy
T -f /dev/null new-session -d -x 200 -y 20 -- env -i HOME="$HOME" TERM=xterm-256color \
  LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/bin:/bin ZKEY_MODE=all \
  bash --norc --noprofile -c "exec bash --rcfile '$PLUGIN' -i" \
  || { echo "NOT_MEASURABLE: tmux session did not start"; finish 2; }
ready=""
for _ in $(seq 1 50); do
  T send-keys -l -- "touch $OUT/ready" ; T send-keys Enter
  sleep 0.1; [ -e "$OUT/ready" ] && { ready=1; break; }
done
[ -n "$ready" ] || { echo "NOT_MEASURABLE: interactive bash never ran a command"; finish 2; }

machine() { T send-keys -l -- "$1"; T send-keys Enter; }
human() {  # one key per tmux call, ~60 ms apart (fast human typist)
  local s=$1 i
  for ((i = 0; i < ${#s}; i++)); do T send-keys -l -- "${s:i:1}"; sleep 0.06; done
  T send-keys Enter
}
fast() {  # one key per tmux call, ~30 ms apart: still a person, not one write
  local s=$1 i
  for ((i = 0; i < ${#s}; i++)); do T send-keys -l -- "${s:i:1}"; sleep 0.03; done
  T send-keys Enter
}
wait_file() { local f=$1; for _ in $(seq 1 50); do [ -s "$f" ] && return 0; sleep 0.1; done; return 1; }

fail=0
check() {  # name expected file
  if ! wait_file "$3"; then echo "FAIL $1: command never ran"; fail=1; return; fi
  local got; got=$(cat "$3")
  if [ "$got" = "$2" ]; then echo "PASS $1: $got"; else echo "FAIL $1: expected=[$2] actual=[$got]"; fail=1; fi
}
secret='project_doc_max_bytes PROJECTS_ROOT Bash(git reset:*)'
for round in 1 2 3; do
  machine "printf '%s\n' '$secret' > $OUT/m$round"
  check "M$round machine-typed" "$secret" "$OUT/m$round"
done
human "printf '%s\n' 'project_doc_max_bytes PROJECTS_ROOT' > $OUT/i"
check "I human-typed identifiers" "project_doc_max_bytes PROJECTS_ROOT" "$OUT/i"
human "printf '%s\n' 'tieengs vieetj' > $OUT/h"
check "H human-typed Vietnamese in quotes" "tiếng việt" "$OUT/h"
human "printf '%s\n' tieengs vieetj > $OUT/h2"
check "H2 human-typed Vietnamese unquoted (default all)" $'tiếng\nviệt' "$OUT/h2"
fast "printf '%s\n' tieengs vieetj > $OUT/h3"
check "H3 fast human unquoted" $'tiếng\nviệt' "$OUT/h3"
human "printf '%s\n' sawc > $OUT/s"
check "S unfinished syllable keeps its shape" "săc" "$OUT/s"
machine "printf '%s\n' 'tieengs vieetj' > $OUT/mv"
check "MV machine-typed Vietnamese stays raw" "tieengs vieetj" "$OUT/mv"
machine "printf '%s\n' tieengs vieetj > $OUT/mu"
check "MU machine-typed Vietnamese unquoted stays raw" $'tieengs\nvieetj' "$OUT/mu"
finish "$fail"
