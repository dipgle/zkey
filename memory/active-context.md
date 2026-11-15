# zkey/core — 15/11/2026 16:00 +07 — CHƯA XONG (sản phẩm)

Phiên mở ở gốc ~/projects (CLI Claude). Hà dặn 15:45: làm KHÔNG ảnh hưởng máy đang chạy ⇒ chỉ Xvfb/D-Bus/IBus/tmux riêng, không đụng desktop/IBus hệ thống.

ĐÃ ĐO (chạy thật):
- AN NINH plugin bash (1335266, đã đẩy): lệnh máy gõ không còn bị viết lại; cổng `scripts/accept-shell-tmux.sh` 5/5, đối chứng từng chốt ĐỎ. huba (f3cfa32) nay mở pane với `ZKEY_MODE=off` ⇒ đường huba không còn đo được zkey; khoá hành vi bằng cổng của zkey.
- Gõ dồn + Backspace/Enter: gốc = module IBus GTK bất đồng bộ đẩy phím không nhận ra cuối hàng (`gdk_event_put`). `runtime.py` đặt `IBUS_ENABLE_SYNC_MODE=1` cho app do zkey mở. GTK3 0/30 → 30/30, đối chứng `ZKEY_CLIENT_SYNC_MODE=0` ĐỎ. accept-xvfb 2/2 × 6 bài XANH. Chi phí trung vị +2 ms/phím (6 vs 4 ms, max 8.3).

Việc kế: gõ dồn + phím native trên GTK4 Text Editor (accept-editor chưa có pha này); app ngoài `zkey --run` không có cờ sync. Nợ cũ: `zkey --run ptyxis` IBus chết 1/3; ô mật khẩu GTK3 đỏ 1/~12 (2 lượt gần nhất không tái); tiếng Anh trong nháy; vim/TUI, zsh, SSH; Chrome/Electron (có firefox); P0-001.

Nền: không có. Chạy lại: `bash /mnt/data/projects/zkey/scripts/accept-xvfb.sh` (6 bài, log `.tmp/accept-xvfb.log`).
