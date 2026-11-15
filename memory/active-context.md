# zkey/core — 15/11/2026 21:35 +07 — ĐÃ CÀI ~/.local, dùng được qua `zkey --run` + plugin bash

Phiên Claude mở ở gốc ~/projects. Hà: «làm ra sản phẩm cuối, đừng dừng»; «không ảnh hưởng máy đang chạy».

ĐÃ ĐO (chạy thật, Xvfb/bus/IBus riêng):
- accept-xvfb 7 bài XANH + cổng tác hại «MÁY NGUYÊN»: GTK4 Text Editor, GTK3 (gõ dồn + ⌫/Enter 30/30, IBus sync), VTE ×2, ptyxis, màn thiết lập → ô gõ (hoà→hòa), plugin bash vs lệnh máy gõ.
- Cài thật ~/.local (Hà duyệt 21:2x): bản cài gõ thật XANH. Menu «zkey — Gõ tiếng Việt».
- Bộ gõ hệ thống CHUẨN BỊ, CHƯA BẬT (Hà chọn): `scripts/system-ime.py enable|disable` có sao lưu; `probe-system-ime.py` XANH, đối chứng ĐỎ.
- SỰ CỐ do phiên: accept-ptyxis (từ 11:00) + 1 lệnh tay làm portal tài liệu desktop hỏng; Hà duyệt restart 2 lần (PID 365673). Chốt: private_bus.py + test + cổng tác hại.

Hà đã chọn: trình duyệt BỎ QUA (P0-001 mục 1–2 KHÔNG ĐO ĐƯỢC).
Nợ: phiên GNOME thật sau khi bật bộ gõ hệ thống; Wayland-native; Chrome/Electron (không có trên máy); vim/TUI/zsh/SSH; tiếng Anh trong nháy (Telex mơ hồ); .deb.

Nền: không có. Chạy lại: `bash /mnt/data/projects/zkey/scripts/accept-xvfb.sh`.
