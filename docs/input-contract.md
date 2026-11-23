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

## Hà chốt 21/11 — nhận dấu cho từ ĐÃ CÓ trên màn hình

- «Cứ con trỏ đứng cuối từ là gõ dấu vẫn nhận» (Hà 21/11, trả lời câu hỏi của phiên): một phím dấu (`s f r x j z`) áp vào **từ đứng ngay trước con trỏ**, kể cả từ **không phải do zkey gõ** (dán vào, từ phiên trước, từ tài liệu có sẵn).
- Chốt an toàn giữ nguyên: chỉ phím DẤU (không áp `a`/`w` — không dán chữ vào từ lạ); không làm khi có **bóng chọn**; không làm khi từ dài ≥ `max_keys`; không làm qua **ranh giới không phải chữ cái** (chỉ lấy dãy chữ cái sát con trỏ); không làm ở ngữ cảnh **mật khẩu/TERMINAL/protected** (đường bypass cũ); từ đã **Ctrl/Escape đóng băng** thì chỉ thêm, không sửa.
- Hệ quả so với bản trước: bỏ điều kiện «phải là từ chính engine vừa commit» trong trường hợp con trỏ đứng cuối từ; `docs/input-contract.md` trước đây cấm sửa chữ ngoài ⇒ nay Hà cho phép, có các chốt trên.

## Hà duyệt 22/11 — bộ đệm riêng cho từ ĐẦU TIÊN của ngữ cảnh không gửi snapshot

- Đo 20/11 (ô tìm kiếm Files; trace `engine-trace.log` dòng 2939–2973): ngữ cảnh gửi **một** snapshot `chars=0` lúc tạo rồi `Reset` sau mỗi phím và **không gửi snapshot nữa** ⇒ engine không có bằng chứng sở hữu, cả từ gõ ra thô (`tieengs`, `móiw`).
- Luật mới (Hà duyệt): khi ứng dụng **chưa từng** gửi snapshot sau một commit/Reset trong phiên focus này, engine giữ **bộ đệm riêng** cho từ do chính nó vừa commit và tiếp tục ghép qua các lần `Reset`.
- Chốt an toàn: (a) phải đã từng nhận snapshot trong phiên focus (ứng dụng đã chỉ ra ô nhập) — chưa từng có snapshot thì **không đoán**; (b) bộ đệm chỉ chứa chữ engine vừa commit, không literal/Ctrl-freeze, không span chờ; (c) **snapshot đầu tiên** sau đó phải khớp từ (đúng nội dung, con trỏ, không bóng chọn) thì mới giữ, sai ⇒ xoá bộ đệm và **không sửa gì**; (d) xoá bộ đệm khi FocusOut/Destroy, đổi ContentType, hoặc phím không in được/Ctrl/Escape.
- Rủi ro Hà đã chấp nhận: ứng dụng không báo click/đổi con trỏ ⇒ engine có thể xoá nhầm vài chữ trong chính từ vừa gõ. Không mở rộng cho mật khẩu/TERMINAL/protected.
- Đo: `native/tests/accept_silent_context.py` trên engine ĐÃ CÀI — `tieengs→tiếng`, `mowis→mới`, `remove>0`; đối chứng ngược cùng lượt: không snapshot ⇒ `tieengs`, 0 delete. `scripts/accept-installed.sh` 5/5 GATE 0.

## Hà chốt 23/11 — phím hình áp vào nguyên âm trong cụm («đaua» → «đâu», Firefox)

- Báo cáo của Hà: gõ `ddaua` trên Firefox ra `đaua`, mong `đâu`. Gốc (`compose.rs` `reshape`): phím hình `a/e/o` chỉ áp vào **nguyên âm cuối** (hoặc xuyên một phụ âm cuối); với cụm `au`, phím `a` cuối bị coi là chữ mới nên cả app lẫn terminal đều không ghép (không phải lỗi riêng Firefox — Firefox chỉ là nơi Hà thử).
- Luật mới: phím hình áp vào **nguyên âm khớp gần nhất phía trước**, nhưng chỉ khi **cả từ trước phím và từ sau khi áp đều đánh vần được** (`valid_syllable`). Hệ quả đo được: `đau+a ⇒ đâu`, `au+a ⇒ âu`, `oi+o ⇒ ôi`; giữ nguyên `aoa`, `eue`, `queue` (tiếng Anh), `iao`, `oua`. Không đảo ngược hình đã áp từ xa (`đâu`+`a ⇒ đâua`).
- Đo: unit `a_late_shape_key_reaches_the_matching_vowel_of_the_cluster` (RED `đaua` → GREEN `đâu`); cổng trên engine ĐÃ CÀI `accept_firefox_pattern.py` và `accept_silent_context.py` thêm ca `ddaua ⇒ đâu` (`removes=2`), đối chứng không snapshot ⇒ `ddaua`, 0 delete; `accept-installed.sh` 5/5; `accept-shell-tmux.sh` 10/10; matrix 9/9.

## Nghiệm thu bắt buộc trước đóng P0

1. Input thường trên trình duyệt: kiểm giá trị/input event của ứng dụng thay đổi theo phím, không chỉ quan sát IME.
2. Password/PIN trình duyệt: không Telex, không preedit/candidate/gợi ý, không lưu nội dung.
3. Terminal dùng mật khẩu **giả dùng một lần cho kiểm thử**, tắt ECHO trước phím đầu: không lộ preedit/candidate, không đổi chuỗi, không đợi dấu cách mới nhận. Không dùng hoặc thu mật khẩu thật.
4. Terminal dòng lệnh thường, raw/TUI, SSH/tmux: sửa dấu/Backspace đúng và không mất/nhân ký tự.
5. Đổi focus, chọn chữ, thay vị trí con trỏ và ký tự Unicode tổ hợp: không sửa nhầm vùng hay mang chữ sang ngữ cảnh mới.

Các bước này phải qua giao diện thật. Unit test trả `handled=True`, tắt underline hoặc benchmark core không thay thế được chúng.
