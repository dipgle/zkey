#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Per-key cost of the bash plugin function (shell/zkey.bash) including the
# round trip to zkey-line. Synthetic text only. Not keyboard-to-screen latency:
# excludes the terminal, readline redraw and the compositor.
set -u
exec bash --rcfile /mnt/data/projects/zkey/shell/zkey.bash -i <<'EOF' 2>&1 | grep -oE 'BENCH[^$]*'
set +o emacs +o vi; ZKEY_MODE=quoted
n=2000
start=$EPOCHREALTIME
for ((r = 0; r < n / 7; r++)); do
  READLINE_LINE='echo "' READLINE_POINT=6 ZKEY_TEXT=
  for k in t i e e n g s; do __zkey_key "$k"; done
done
end=$EPOCHREALTIME
[[ $READLINE_LINE == 'echo "tiếng' ]] || echo "BENCH WRONG RESULT"
keys=$(( (n / 7) * 7 ))
us=$(( (${end/./} - ${start/./}) / keys ))
echo "BENCH keys=$keys mean_us_per_key=$us errors=$ZKEY_ERRORS"
EOF
