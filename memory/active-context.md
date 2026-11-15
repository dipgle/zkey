# zkey/core — 15/11/2026 15:40 +07 — CHƯA XONG (sản phẩm)

Phiên mở ở gốc ~/projects (CLI Claude). Đầu phiên: cây sạch, master=origin 1a1184a; không phiên zkey sống; PID fixture cũ (94574/94548) đã chết.

ĐÃ ĐO (chạy thật):
- AN NINH plugin bash (huba báo, Hà giao): lệnh MÁY gõ (tmux send-keys) bị quoted mode viết lại (`git reset`→`git rết` trong --disallowedTools). Sửa `shell/zkey.bash`: còn byte trong hàng đợi (`read -t 0`) ⇒ cả dòng nguyên văn tới khi dòng trống; từ sau ký tự định danh/đường dẫn và từ toàn hoa giữ nguyên. Cổng `scripts/accept-shell-tmux.sh` RED→GREEN 5/5, đối chứng ngược bỏ từng chốt ĐỎ đúng ca. VTE plugin 0/1 + ptyxis thật XANH; Python 45/45; Rust 9/9; audit 140/0.
- Gõ dồn GTK3 có Backspace/Enter xen giữa: ĐỎ 0/30 (pha BURST+NATIVE `scripts/native_acceptance.py`) ⇒ `accept-xvfb.sh` ĐỎ tới khi sửa. Ví dụ `tieengs⏎vieetj`→`tieengsvi⏎eetj`.

Việc kế: tìm gốc gõ dồn + phím native (phím Backspace/Enter đi native bị xếp lại so với commit của engine; `zkey/session.py` key()/`engine.py` apply). Nợ cũ: `zkey --run ptyxis` IBus chết 1/3; ô mật khẩu GTK3 đỏ 1/~12; tiếng Anh trong nháy; vim/TUI, zsh, SSH; Chrome/Electron (có firefox, chưa có chrome); P0-001.

Chờ: huba chạy lại `/terminal`+`/type` để xác nhận phía họ; bash đã mở trước sửa giữ hàm cũ tới khi mở terminal mới.

Nền: không có. Chạy lại: `bash /mnt/data/projects/zkey/scripts/accept-shell-tmux.sh`; `bash /mnt/data/projects/zkey/scripts/accept-xvfb.sh`.
