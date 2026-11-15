#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Install / uninstall the zkey bash plugin in ~/.bashrc (one marked block).
# Idempotent; backs up ~/.bashrc first; checks syntax after editing.
#   bash scripts/install-shell.sh            install
#   bash scripts/install-shell.sh --uninstall
set -u
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
RC=${ZKEY_BASHRC:-$HOME/.bashrc}
BEGIN='# >>> zkey shell plugin >>>'
END='# <<< zkey shell plugin <<<'

if [ ! -x "$ROOT/target/release/zkey-line" ]; then
  echo "zkey: $ROOT/target/release/zkey-line chưa build (cargo build --offline --release)"; exit 2
fi
touch "$RC"
backup="$RC.zkey-backup.$(date +%Y%m%d%H%M%S)"
cp -p "$RC" "$backup"
# Remove an existing block (also the uninstall path).
tmp=$(mktemp "$RC.zkey.XXXXXX")
awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1;next} $0==e{skip=0;next} !skip' "$RC" > "$tmp"
if [ "${1:-}" != "--uninstall" ]; then
  printf '%s\n# Gõ tiếng Việt Telex trên dòng lệnh: Alt+Z đổi chế độ, zkey-status xem trạng thái.\n[ -r %q ] && source %q\n%s\n' \
    "$BEGIN" "$ROOT/shell/zkey.bash" "$ROOT/shell/zkey.bash" "$END" >> "$tmp"
fi
if ! bash -n "$tmp"; then
  rm -f -- "$tmp"; echo "zkey: cú pháp ~/.bashrc mới lỗi; giữ nguyên tệp cũ (sao lưu $backup)"; exit 1
fi
cat "$tmp" > "$RC" && rm -f -- "$tmp"
blocks=$(grep -c -x -F "$BEGIN" "$RC")
echo "zkey: ${1:-install} xong; khối zkey trong $RC = $blocks; sao lưu $backup"
