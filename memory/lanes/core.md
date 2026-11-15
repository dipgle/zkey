# core — 15/11 01:00 +07, chưa xong

User cần bộ gõ dùng được, không dừng ở báo cáo. Đã viết commit từng phím/suffix sửa có xác nhận; prototype preedit đã thay. Rust 7/7, clippy/release0; Python/trace33/33; audit8 tệp/114 assertion0; stage9/9; protocol7 nhóm0.

## NỢ MỞ CỦA LÀN

- P0-001: nghiệm thu app thật chưa đạt, terminal/cross-app còn mở. Không có backend Telex VTE, không giả Backspace. Client thiếu surrounding/ack hoặc protected/TERMINAL nhận nguyên trạng.
- IBUS_USE_PORTAL='0' thực tế bật portal: đã unset và truyền private activation env. Chưa xanh UI sau sửa. Đã RÚT kết luận GTK cũ thiếu đối chiếu engine.
- Compositor từ chối tự activation. Đang chờ user bấm vùng soạn thảo Text Editor; chạy tiếp `scripts/accept-editor.py` qua huba, phải xanh per-key + 10 burst và xác nhận private engine.
- Visual chưa đo: ảnh XGetImage cũ trắng/đen không tính. Settings, Chrome/Electron, VTE ECHO-off, gói Ubuntu, corpus/tiếng Anh/VNI/audit config/giấy phép còn mở.

Nền editor: PID94574/supervisor94548, marker `.tmp/editor-app.json`, log `.tmp/editor-session.log`; không test nền. Brief kế nhiệm `.tmp/brief-core-ke-nhiem-20261115-0100.md`. Cây chưa commit/remote; QG Linux chưa đo.
