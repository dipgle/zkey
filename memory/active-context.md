# zkey/core — native rewrite (16/11 18:30, phiên claude acc6 PID2418069)

Hà giao VIẾT LẠI native, tự thiết kế/code/kiểm. Phiên trước (ses_e1dc…) không thấy tiến trình, ghi cuối 13:13; diff của nó đã gom 4 commit (8986445 6be19c0 99d03a1 6286b4f). Chưa push.

ĐÃ ĐO 16/11 tối: native Rust 40/40 (+2 corpus) clippy0 fmt0; legacy Rust/clippy0; Python 79/79; map 216 nút/136 bài.
- N06: corpus Telex 134 dòng/251 phép (8c416db); mutant ê/ơ ⇒ĐỎ 11/251, khôi phục XANH. impact.py trước đó KHÔNG quét native/tests/*.rs (RED→GREEN).
- DESKTOP THẬT: Hà đã đăng nhập GNOME Wayland tty2. fcitx5 (autostart người dùng) giữ org.freedesktop.IBus ⇒ ibus GNOME failed ⇒ zkey KHÔNG nhận phím, nguồn gõ chỉ còn xkb us. Sửa system-ime.py: enable ẩn autostart fcitx5 + verify (e4af712). `system-ime.py verify` máy thật = mã1 fcitx5. CHƯA áp lên máy.

CHỜ HÀ: (1) áp lên máy: `system-ime.py disable` rồi `enable` (ẩn fcitx5) + đăng xuất/vào, sau đó `verify` phải 0; (2) publish site có email lên zkey.dipgle.com — web-driver đang ĐĂNG NHẬP tfl5 (Operator) trên Xvfb riêng; (3) N01 WebKit: hợp đồng cấm preedit (docs/input-contract.md:5) ⇒ chỉ còn báo lỗi upstream WebKitGTK/bridge cho app do zkey mở.

KẾ (tự làm được): N04 backend terminal native; N06 tiếp (VNI/tiếng Anh cần Hà chốt chính sách).
Nền: web-driver.py (PID286546, Xvfb :99) — dừng: .tmp/web-driver/cmd.json {"id":41,"op":"quit"}. Không job test nền.
