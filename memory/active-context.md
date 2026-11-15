# zkey/core — 15/11/2026 08:00 +07 — CHƯA XONG (sản phẩm), mạch gõ GTK XANH

Phiên acc6 (CLI 120194). Repo public dipgle/zkey, master=8721a29 (đã đo ls-remote). Phiên Codex cũ PID9467 đã đóng 09:0x (đứng yên từ 05:56, cây sạch+đã đẩy; pts/5 còn bash).

ĐÃ ĐO (chạy thật): `bash scripts/accept-xvfb.sh` GATE_EXIT=0, 3/3 lượt — GTK4 Text Editor 7 tiền tố + «tiếng việt» (AT-SPI, engine 20 key-state, cổng ≥7); GTK3 7 tiền tố + 10 lượt gõ dồn 0 ms + Backspace/Home + ô mật khẩu đi thẳng + 0 preedit/warning. Ảnh `.tmp/native-gtk-render.png`. Python 44/44, Rust 7/7, clippy/release 0, impact record 0, audit 138 assertion 0. Chi tiết `docs/verification.md` mục 08:00.

Sửa gốc: phím trả native bị GTK async xếp sau commit ⇒ `tieseng`. `zkey/session.py` nay commit mọi phím in được; chưa xác nhận ⇒ commit nguyên dạng; ghép bù khi ảnh chụp app khớp nguyên văn (hậu tố + ranh giới, ≤3 từ/64 ký tự); `engine.py` ghép bù trong `do_set_surrounding_text`. Đối chứng ngược 2 chiều đã chạy.

Xvfb: `.tmp/tools/root/usr/bin/Xvfb` (apt-get download + dpkg-deb -x; sudo hết giờ, không cài hệ thống). Desktop Xwayland `-enable-ei-portal` bắt hộp thoại RemoteDesktop mỗi phiên XTest; chủ máy xem qua zigeel không thấy ⇒ không dùng desktop để tự động.

Việc kế: terminal bash XANH qua plugin `shell/zkey.bash` (README mục Terminal; chưa thêm vào ~/.bashrc). Tiếp: tiếng Anh trong nháy, vim/TUI, zsh, SSH; gõ dồn xen Backspace/Enter; Chrome/Electron; Wayland-native. Chạy toàn bộ: `bash scripts/accept-xvfb.sh`.

Nền: fixture desktop Text Editor PID94574/supervisor94548 vẫn mở từ 00:58 (marker `.tmp/editor-app.json`). Không job nền khác. Chạy lại: `bash /mnt/data/projects/zkey/scripts/accept-xvfb.sh`.
