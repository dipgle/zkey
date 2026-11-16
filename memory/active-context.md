# zkey/core — native rewrite (17/11 00:35, phiên claude acc6)

Hà giao VIẾT LẠI native, tự thiết kế/code/kiểm. Diff phiên trước đã gom commit; cây sạch, CHƯA push.

ĐÃ ĐO 16/11 tối: native Rust 40/40 clippy0 fmt0; Python 79/79; map 216 nút/136 bài. N06 corpus 251 phép (8c416db).

BỘ GÕ HỆ THỐNG — ĐÃ ÁP (Hà «làm đi» 18:40, vượt zkey/CLAUDE.md:8 có duyệt): disable (hoàn nguyên đúng byte, hash 2261b5…/8447b7…) rồi enable bản mới (e4af712+4103d50): autostart fcitx5 Hidden=true (sao lưu ~/.local/state/zkey/system-ime/fcitx5-autostart.orig), 99-zkey.conf ghi đè cả QT_IM_MODULES/SDL_IM_MODULE, nguồn gõ [xkb us, ibus zkey]. Generator systemd tính đúng 7 biến. fcitx5 cũ còn chạy tới khi đăng xuất ⇒ `system-ime.py verify` hiện vẫn mã1.

17/11 00:35: Hà CHƯA đăng xuất (gnome-shell từ 16/11 10:10). Linger=yes ⇒ systemd --user sống qua đăng xuất, env còn QT_IM_MODULES/SDL_IM_MODULE=fcitx ⇒ PHẢI KHỞI ĐỘNG LẠI MÁY. `verify` nay so cả env trình quản lý (commit kế 7f98cec).
KẾ NGAY SAU KHI HÀ KHỞI ĐỘNG LẠI: `python3 scripts/system-ime.py verify` phải 0; xem nguồn gõ còn ('ibus','zkey'); gõ thật Text Editor/Firefox/terminal (cần Hà gõ hoặc RemoteDesktop). Hỏng ⇒ `system-ime.py disable` + khởi động lại.

Web: KHÔNG publish (luật gốc cấm Claude deploy prod; ngoại lệ chỉ zigeel.com). web-driver đã quit 18:45 (phiên Operator đóng). Hà tự tải `site/index.html` (8881 byte, sha256 49ea7571…) lên tfl5 app zkey.
N01: chờ Hà chọn (báo upstream WebKitGTK / bridge chỉ cho app do zkey mở). Preedit bị hợp đồng cấm.
Nền: KHÔNG CÓ.
