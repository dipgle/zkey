# Kết quả 2026-11-14 — prototype, CHƯA nghiệm thu sản phẩm

## 15/11 08:00 — GTK4 + GTK3 gõ thật XANH trên Xvfb riêng (3/3 lượt)

- Đường đo: `bash scripts/accept-xvfb.sh` → `.tmp/accept-xvfb.log` (GATE_EXIT 0/1/2). Xvfb 21.1.22 tải bằng `apt-get download` + `dpkg-deb -x` vào `.tmp/tools` (không cài hệ thống; sudo hết giờ). Phím XTest chỉ vào màn ảo, bus D-Bus/IBus riêng.
- Vì sao không dùng desktop: Xwayland chạy `-enable-ei-portal` ⇒ mỗi phiên XTest bật hộp thoại RemoteDesktop; chủ máy xem qua zigeel từ xa không thấy. Desktop chỉ xanh 1 lượt (07:14) khi quyền đang mở.
- GNOME Text Editor (GTK4): 7 tiền tố + «tiếng việt» đọc qua AT-SPI; vết engine riêng 20 `key-state`; cổng đòi ≥7.
- GTK3: 7 tiền tố, 10 lượt gõ dồn 0 ms, Backspace native, Home, ô mật khẩu đi thẳng (2 chấm), 0 preedit, 0 warning. Ảnh `.tmp/native-gtk-render.png` đã xem.
- RED trước sửa (cùng bài): `tieseng vieetj` — phím trả native bị GTK async xếp sau commit ⇒ xáo thứ tự. Sửa `zkey/session.py`: commit mọi phím in được; phím chưa xác nhận commit nguyên dạng; ghép bù khi ảnh chụp của app khớp nguyên văn (hậu tố + ranh giới, ≤3 từ/64 ký tự).
- Python 44/44; đối chứng ngược: bỏ luật ranh giới ⇒ test âm ĐỎ; bỏ chốt private ở ghép bù ⇒ test mật khẩu ĐỎ (test cũ mù, đã sửa). Rust 7/7, clippy 0, release 0; impact record 0; audit 8 tệp/138 assertion 0.
- CHƯA ĐO: desktop Wayland-native, Chrome/Electron, terminal/VTE (P0-001), Backspace trong lúc gõ dồn, đo trễ.

## 15/11 00:59 — ĐANG LÀM, rút phạm vi nghiệm thu UI

Đường sản phẩm nay commit từng phím, sửa suffix theo incoming surrounding. Python 33/33; Rust 7/7; clippy -D warnings/release build mã 0. Protocol host 7 nhóm mã 0, 0 warning sau giữ GI Text wrapper để tránh libibus kiểm floating object đã hết vòng đời. Test compile mọi Python entrypoint giữ lỗi duplicate lambda argument từng làm probe không khởi động.

Các lượt GTK3/XTest smoke trước chưa chứng minh engine xử lý chính là zkey private: **không dùng chúng làm nghiệm thu zkey**. Root cause nối GTK: `IBUS_USE_PORTAL="0"` vẫn bật portal (binary kiểm biến tồn tại), trong khi service portal không nhận địa chỉ daemon riêng. Đã unset biến và truyền activation env vào bus riêng. Bài native mới đòi vết key-state của zkey; chưa xanh sau sửa này.

Lượt mới: desktop không khoá, modifier không giữ (`scripts/desktop-status.py`); compositor từ chối kích hoạt GNOME và GTK fixture nên dừng trước gõ. `.tmp/editor-app.json` là app còn mở; `.tmp/native-acceptance.log` còn đỏ môi trường. Đã hỏi chủ máy bấm vào vùng soạn thảo. Chưa kiểm burst 10 phrases, VTE ECHO-off, Chrome/Electron hay visual. Ảnh trắng/đen trước không tính là nghiệm thu. Không cài hoặc đổi input source toàn hệ thống. Các bảng dưới là lịch sử prototype.

## Lượt 23:49 — giảm rủi ro P0, chưa đóng P0

- Diff `zkey/engine.py`, `tests/test_engine.py`: graph chọn 9 nút, 7/34 test; đã chạy 7 handler test rồi toàn bộ 27 Python test, mã 0. `impact.py --record` cũng chạy 27/27, mã 0 và cập nhật graph/vết gọi thật. Không đổi Rust, không chạy lại Rust/build/clippy trong lượt này.
- RED trước sửa: 2 test mới thất bại (bypass TERMINAL, xoá transport preedit khi chuyển protected). Test reset mở rộng cũng đỏ riêng trước khi sửa reset. GREEN sau: 27/27 Python.
- Bypass được kiểm bằng 6 loại phím giả; chuyển protected kiểm 5 trường hợp TERMINAL/PASSWORD/PIN/PRIVATE/HIDDEN_TEXT, reset/focus-out, trở lại FREE_FORM và commit đúng một chữ mới. Sink chạy `Engine.apply` thật rồi thu lời gọi update/commit; không có client IBus, ECHO-off hoặc UI thật. Không thu nội dung người dùng.
- `audit_measurements.py`: 7 tệp/101 assertion, 0 mẫu nghi ngờ trong tập nhận diện, mã 0. Đã soát ngữ nghĩa test mới; phép đếm kết quả tránh `all([])` xanh rỗng.
- Stage lại trong repo, mã 0; đối chiếu SHA-256 nguồn và bundle 7/7 tệp Python/thư viện khớp, mã 0. Không cài ra ngoài repo. Stat hai tệp mã/test lúc 23:50 khớp cỡ/mtime sau lần sửa cuối.
- Chưa nghiệm thu desktop; engine chỉ bypass terminal được khai báo đúng. FREE_FORM vẫn giữ từ trong preedit. Không đổi cấu hình input source hoặc cài ra ngoài repo. QG chưa chạy; chưa gom commit/phát hành.

## Đã chạy tại `/mnt/data/projects/zkey`

Bảng dưới ghi lượt prototype trước 23:49; số Python mới ở mục trên.

| Phép kiểm | Kết quả |
| --- | --- |
| `cargo test --offline` | 7/7 test Rust, mã 0 |
| `cargo clippy --offline --all-targets -- -D warnings` | mã 0, không warning |
| `cargo build --offline --release` | mã 0, sinh cdylib + benchmark |
| `python3 scripts/impact.py --record` | 25/25 test Python; import graph bổ sung call trace thật |
| `python3 scripts/audit_measurements.py` | 7 tệp, 79 assertion, 0 mẫu đáng ngờ trong tập nhận diện; mã 0 |
| `python3 scripts/stage.py` | mã 0; chỉ ghi `.tmp/stage` |

Các lượt RED→GREEN đã quan sát và giữ test: lỗi chuyển `uwow`; Backspace xoá phím thay vì ký tự; thiếu `ua+w → ưa`. Cũng đã sửa khác biệt GI `keyval_to_unicode` trả chuỗi. Test handler có cấy lỗi core để kiểm raw text được giữ đúng một lần; test bản đồ và bộ quét có đối chứng ngược.

Benchmark release, 100.000 lần replay tiền tố của 5 từ, sau warm-up: p50 **96 ns**, p95 **1.222 ns**, p99 **2.398 ns**, max **39.652 ns**. Đo `Instant` quanh hàm Rust; không gồm ctypes/Python, IBus, compositor, ứng dụng hoặc màn hình. Đây không phải bằng chứng mượt hơn bộ gõ khác.

## Chưa đo được / còn thiếu

Lệnh thăm dò `dbus-run-session` bị sandbox từ chối bind socket: mã **127**, không phải đỏ nghiệp vụ hoặc xanh. Đã ghi scratchpad huba đúng session; tệp được đổi thành `huba-run.taken-20261114T153641Z`. Chưa có `.tmp/ibus-probe.log` ở lần kiểm cuối. “Đã nhận thư” không đồng nghĩa “đã chạy”. Lệnh tiếp tục: `bash /mnt/data/projects/zkey/scripts/probe-host.sh`.

Ngoại lệ đi thẳng API: probe dùng `InputContext` cho **thăm dò protocol**, không tạo dữ liệu nghiệp vụ và không tuyên bố E2E. Bù bằng nghiệm thu gõ thật qua UI còn mở. Probe đã sửa thứ tự focus trước chọn engine qua soát source/runtime IBus; chưa được chạy thành công.

Chưa bật engine trên desktop; chưa đo latency phím→màn hình; chưa kiểm Chrome/VS Code/terminal, focus commit thực tế, màn thiết lập GTK hoặc Wayland/X11. Chưa chạy QG và chưa phát hành/gom commit. Chưa chọn giấy phép phát hành.

Soát bảo mật trên mã: không mạng/clipboard/global keyboard hook, không log nội dung gõ; config lưu user-local mode 0600; password/PIN/private hints được bỏ qua. Chỉ có test kỹ thuật cho các nhánh này, chưa xác nhận app thật khai báo input purpose đúng. Chưa có audit thay cấu hình, ghi nợ trước phát hành.

Nguồn: `src/lib.rs`, `src/telex.rs`, `zkey/engine.py`, `zkey/session.py`, `tests/test_engine.py`, `tests/test_session.py`, `scripts/probe_ibus.py`. Tính đúng toàn bộ tiếng Việt chưa được chứng minh bởi tập test hữu hạn này.
