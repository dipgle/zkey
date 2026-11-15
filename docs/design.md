# Thiết kế bản thử

**Cập nhật 15/11:** đã thay prototype preedit bằng commit theo từng phím và surrounding-text xác nhận. P0-001 vẫn chặn phát hành toàn hệ thống; terminal chưa có backend Telex được kiểm chứng. Xem `docs/input-contract.md`.

## Vấn đề và bằng chứng

Người dùng phản ánh gõ trên Ubuntu kém mượt Windows. Chưa xác định được nguyên nhân cụ thể. Độ trễ có thể nằm ở core, IBus, compositor hoặc ứng dụng; benchmark core không trả lời toàn bộ vấn đề.

## Đường nhập liệu

Phím → IBus → adapter Python/GObject → lõi Rust → commit phần chữ mới vào ứng dụng. Thêm dấu: kiểm snapshot do ứng dụng gửi, rồi delete-surrounding suffix cần đổi + commit suffix mới. Không giả Backspace, không clipboard, không đọc thiết bị bàn phím toàn hệ thống. Đổi focus/reset xoá lịch sử soạn, không commit lại.

Chỉ snapshot từ callback ứng dụng được dùng để sửa; không đọc cache đã bị libibus sửa lạc quan để tuyên bố app nhận thành công. Snapshot rỗng khởi động chỉ cho phép lần chèn đầu tiên, bị vô hiệu trước edit. Thiếu ack/capability thì pass-through. Phải đo burst thật: unit sink ack đồng bộ không chứng minh scheduling desktop.

`zkey.launch` + `zkey.runtime` mở IBus và ứng dụng trong bus riêng, cấu hình/cache/data thử dưới `.tmp`, không đổi input source hệ thống. Launcher giám sát daemon/engine; nếu chết, báo lỗi để người dùng lưu tài liệu, không âm thầm quảng bá Telex còn chạy.

Bẫy môi trường đã truy tới binary: libibus tại `0x1c7ac–0x1c7c7` kiểm sự tồn tại của `IBUS_USE_PORTAL`, không kiểm giá trị; chuỗi `"0"` vẫn bật portal. Runtime phải bỏ biến cho client host nối trực tiếp; portal được kích bởi bus riêng phải nhận `IBUS_ADDRESS` riêng qua UpdateActivationEnvironment. Không dùng GTK smoke thiếu vết engine làm nghiệm thu zkey. X11 focus khác cửa sổ active của compositor; bài UI phải kiểm cả hai và dừng trước gõ nếu không kích hoạt được.

Lõi nhận Telex và phần tiếng Việt NFC còn lại sau khi sửa, trả UTF-8, xử lý từng từ có giới hạn độ dài; không mạng, đĩa hoặc log nội dung trên đường xử lý phím. Backspace xoá một ký tự hiển thị, giữ dấu của phần còn lại; gõ tiếp vẫn biến đổi được. Escape hoàn nguyên chuỗi phím kể từ lần xoá gần nhất. Mặc định dùng cách đặt dấu hiện đại (hoà, thuý); cho chọn cách truyền thống (hòa, thúy).

## Cụm tệp và xung đột

- `src/`: core + FFI + benchmark; luồng chính viết.
- `zkey/`: state machine IBus + config + settings; luồng chính viết.
- `tests/`: test adapter/config/protocol; luồng chính viết.
- `scripts/`: bản đồ phụ thuộc trích từ mã và lệnh kiểm; luồng chính viết.
- Agent phụ chỉ thăm dò IBus read-only, không ghi và không git đổi trạng thái.

## Nghiệm thu cần có

1. Test core: Telex, tone migration, hoàn nguyên, Unicode và biên FFI.
2. Test state machine/protocol: commit, pass-through, modifiers, lifecycle; đây là kiểm kỹ thuật, không phải E2E UI.
3. Desktop thật: Chrome/Electron/GTK/terminal, đổi focus khi đang gõ, chọn chữ, password, repeat/backspace, phím tắt và gõ nhanh. Thu trace thời gian không thu nội dung.
4. So sánh với bộ gõ hiện tại trên cùng máy, ứng dụng, nội dung và nhịp gõ. Chỉ lúc đó mới đánh giá độ mượt.

Không áp dụng Playwright cho cửa sổ native IBus/GTK. Nghiệm thu trình duyệt về sau phải đi qua giao diện thật và cơ chế nhập của hệ điều hành; chèn text bằng DOM không kiểm được bộ gõ.
