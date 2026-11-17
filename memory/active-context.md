# zkey/core — native rewrite (17/11 09:52, phiên claude acc6)

Hà giao VIẾT LẠI native. Cây sạch sau mỗi commit, CHƯA push. Rust 40/40 clippy0 fmt0 (16/11); Python 80/80 (17/11).

BỘ GÕ HỆ THỐNG ĐÃ ÁP (Hà duyệt 16/11 18:40, vượt CLAUDE.md:8): autostart fcitx5 Hidden=true (bản gốc ~/.local/state/zkey/system-ime/), 99-zkey.conf ghi đè cả QT_IM_MODULES/SDL_IM_MODULE, nguồn [xkb us, ibus zkey].
17/11: Hà CHƯA đăng xuất (gnome-shell từ 16/11 10:10). Linger=yes ⇒ systemd --user giữ env cũ qua đăng xuất ⇒ PHẢI KHỞI ĐỘNG LẠI. `verify` nay so cả env trình quản lý (c96c224) ⇒ đang mã 1 đúng.

PHIÊN ẨN 07:12 (`scripts/accept-headless-gnome.py login`): gnome-shell --headless, bus riêng, bản chép cấu hình; env mới 5 biến ibus; fcitx5 không chạy; ibus-daemon giữ IBus; phím Mutter RemoteDesktop «Tieengs Vieejt» ⇒ GTK4 «Tiếng Việt» XANH. `control-squatter` ⇒ mã 1. Dconf thật không đổi. Lượt chập chờn = trễ do load ~24 (không mất phím); bộ dò nay chờ chữ đúng ⇒ 3/3 XANH.

GỠ fcitx5 ĐÃ XONG 09:50 (Hà gõ mật khẩu, GATE_EXIT=0): 13 gói remove (không purge, không autoremove); /usr/bin/fcitx5, dbus service, autostart hệ thống đều đã vắng. PID 119222 cũ còn chạy tới khi KHỞI ĐỘNG LẠI.

KẾ SAU KHI HÀ KHỞI ĐỘNG LẠI: `python3 scripts/system-ime.py verify` phải 0; nguồn còn ('ibus','zkey'); gõ thật Text Editor/Firefox/terminal. Hỏng ⇒ `system-ime.py disable` + khởi động lại.
Web: không publish (luật cấm deploy prod); Hà tự tải site/index.html. N01: chờ Hà chọn (báo upstream / bridge).
Nền: KHÔNG CÓ.
