# Hợp đồng nhập liệu — bổ sung 2026-11-14

## Yêu cầu chủ dự án vừa xác nhận

- Ứng dụng nhận ký tự ngay khi gõ; không giữ cả từ trong preedit rồi chỉ gửi khi có dấu cách.
- Trải nghiệm nhất quán giữa trình soạn thảo, trình duyệt và terminal.
- Mật khẩu không bị vẽ trong preedit/candidate và không bị Telex biến đổi. Không chỉ che nét gạch chân.
- Ô mật khẩu trên trình duyệt/điện thoại là ví dụ về ngữ nghĩa do ứng dụng cung cấp; không suy rộng thành mọi input đều phải tắt Telex.

## P0-001 — đường preedit hiện tại không đạt

`zkey/session.py:60–62` tính văn bản nhưng trả `preedit`, chưa commit từng ký tự. `zkey/engine.py:26` gắn underline và `:27` gửi preedit; chỉ `:29` mới commit khi có kết quả flush. Đây là lựa chọn kiến trúc không phù hợp yêu cầu vừa làm rõ, không phải lỗi CSS hoặc tốc độ core.

Trước lượt 23:49, handler chỉ bỏ xử lý PASSWORD/PIN/private hints. PTY có thể tắt echo mà input context vẫn là TERMINAL. Handler nay thêm bypass bắt buộc cho TERMINAL (`zkey/engine.py:56–67`): không giữ phím để Telex, không có lựa chọn bật lại khi chưa có backend được kiểm chứng. Khi chuyển sang ngữ cảnh này hoặc PASSWORD/PIN/private hints, engine xoá bộ đệm và gửi preedit rỗng trước hide, không commit phần đang soạn. Reset cũng gửi preedit rỗng.

Đã kiểm lời gọi transport bằng dữ liệu giả, chưa kiểm client IBus/PTY/UI. Terminal khai FREE_FORM hoặc không cập nhật purpose vẫn có thể đi qua composition. **Chặn phát hành và không dùng prototype cho bí mật thật.** Bypass không phải hỗ trợ gõ tiếng Việt trong terminal; yêu cầu nhận từng ký tự ngoài bypass vẫn chưa đạt.

## Bằng chứng tại máy — thăm dò, không phải nghiệm thu UI

- `/home/user1/.config/fcitx5/conf/unikey.conf:18`: SurroundingText=True; `:20`: ModifySurroundingText=False; `:22`: DisplayUnderline=True. Comment `:19` ghi tính năng sửa surrounding là experimental, `:21` ghi underline thuộc preedit. Không sửa cấu hình này. Tệp chỉ chứng minh cấu hình lưu trên đĩa, không chứng minh engine đang hoạt động trong cửa sổ cụ thể.
- `/usr/include/asm-generic/termbits.h:128,130`: ICANON và ECHO là cờ terminal riêng. IBus content type chỉ có purpose và hints, GI xác nhận PASSWORD=8/PIN=9/TERMINAL=10.
- Soát binary VTE GTK4 0.84.0-2 tại `/usr/lib/x86_64-linux-gnu/libvte-2.91-gtk4.so.0`: `0x7d41d–0x7d42b` đặt input-purpose=10; callback retrieve-surrounding ở `0xa8bd0` và delete-surrounding ở `0xa8be0` trả FALSE. Đây là bằng chứng tĩnh cho bản cài, chưa quan sát một lượt nhập mật khẩu thật.
- IBus Engine `commit_text`/`delete_surrounding_text` trả void; không có xác nhận sửa thành công tại ứng dụng trong giá trị trả về. Không được coi việc gọi hàm là bằng chứng ứng dụng đã nhận đúng.

## Hệ quả thiết kế

Không thể hứa một engine IBus sẽ sửa chữ đã commit an toàn trong mọi terminal chỉ bằng surrounding text. Telex vẫn cần sửa ký tự trước đó (`a` đã nhận, `s` đổi thành `á`). Muốn gửi ngay phải có cơ chế sửa tương thích với đích nhận. Backspace giả không có cùng nghĩa trong readline, raw mode, TUI, SSH/tmux hay lúc nhập bí mật.

Hướng tiếp cần đo: tích hợp hợp tác với terminal/toolkit để có trạng thái nhập đáng tin và thao tác sửa có thể kiểm chứng. Khi chưa có đường đã được kiểm chứng, phải có bypass nguyên trạng cho ngữ cảnh đó và báo rõ chưa hỗ trợ; không gọi đây là hỗ trợ Telex đồng nhất. Nhận diện theo nội dung prompt/cửa sổ hoặc đọc bàn phím toàn hệ thống không phải giải pháp bảo mật.

## Nghiệm thu bắt buộc trước đóng P0

1. Input thường trên trình duyệt: kiểm giá trị/input event của ứng dụng thay đổi theo phím, không chỉ quan sát IME.
2. Password/PIN trình duyệt: không Telex, không preedit/candidate/gợi ý, không lưu nội dung.
3. Terminal dùng mật khẩu **giả dùng một lần cho kiểm thử**, tắt ECHO trước phím đầu: không lộ preedit/candidate, không đổi chuỗi, không đợi dấu cách mới nhận. Không dùng hoặc thu mật khẩu thật.
4. Terminal dòng lệnh thường, raw/TUI, SSH/tmux: sửa dấu/Backspace đúng và không mất/nhân ký tự.
5. Đổi focus, chọn chữ, thay vị trí con trỏ và ký tự Unicode tổ hợp: không sửa nhầm vùng hay mang chữ sang ngữ cảnh mới.

Các bước này phải qua giao diện thật. Unit test trả `handled=True`, tắt underline hoặc benchmark core không thay thế được chúng.
