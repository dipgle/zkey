# zkey/core — 15/11/2026 21:15 +07 — gói dùng được, chờ Hà 3 quyết định

Phiên Claude mở ở gốc ~/projects. Hà: «làm ra sản phẩm cuối, đừng dừng»; «không ảnh hưởng máy đang chạy».

ĐÃ ĐO (chạy thật, Xvfb/bus/IBus riêng):
- accept-xvfb 7 bài XANH + cổng tác hại «MÁY NGUYÊN» (mount /run/user/1000/doc trước=sau): GTK4 Text Editor + GTK3 (gõ dồn + ⌫/Enter 30/30, IBus sync), VTE ×2, ptyxis, màn thiết lập → ô gõ (hoà→hòa), plugin bash vs lệnh máy gõ.
- Gói user-local `scripts/install-user.py` (manifest SHA-256, gỡ an toàn): gõ thật bằng bản cài XANH; lõi hỏng ĐỎ.
- SỰ CỐ do phiên: bài accept-ptyxis (từ 11:00) + 1 lệnh tay làm portal tài liệu desktop mất mount/failed; Hà duyệt restart 2 lần (PID 365673). Chốt lớp: `scripts/private_bus.py` + `tests/test_private_bus.py` + cổng tác hại.

CHỜ HÀ: (1) cài thật vào ~/.local; (2) tải Firefox tarball (classifier chặn curl qua huba) để nghiệm thu trình duyệt — snap trên Xvfb = KHÔNG ĐO ĐƯỢC; (3) bộ gõ hệ thống (component IBus + IBUS_ENABLE_SYNC_MODE=1 cho phiên; GTK4 async mất phím với MỌI engine).

Nợ: Wayland-native, Chrome/Electron (không có trên máy), vim/TUI/zsh/SSH, tiếng Anh trong nháy (Telex mơ hồ), .deb, `zkey --run ptyxis` chết 1/3 cũ không tái hiện.

Nền: không có. Chạy lại: `bash /mnt/data/projects/zkey/scripts/accept-xvfb.sh`.
