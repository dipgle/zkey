# zkey/core — native (22/11)

ĐÃ LÀM + ĐÃ CÀI (engine cài = build `7013c097…`, `native-ime.py` disable/enable 0/0):
(1) **Bộ đệm từ đầu tiên** (Hà duyệt 22/11, `session.rs`): `published`/`reports_caret`/`blind` — `Reset` sau commit chỉ xoá từ khi app **đã từng** gửi lại snapshot; ngữ cảnh câm (ô Files, Telegram web) giữ bộ đệm riêng của engine và ghép tiếp (`tieengs→tiếng`, `mowis→mới`); snapshot sai `owns()`/FocusOut/đổi ContentType/phím không in ⇒ xoá bộ đệm, không sửa gì; app **chưa từng** gửi snapshot ⇒ không đoán (0 delete). Test RED→GREEN 4 bài + 3 chốt an toàn; cổng `native/tests/accept_silent_context.py` (2 chiều trong 1 lượt) — `accept-installed.sh` **5/5 GATE 0**.
(2) **Terminal `sawc`:** `compose.rs` tách `valid_syllable` (hình thái, dùng ghép) ↔ `spell_ok` (bảng chính tả Hà `ư/ô/ơ/ă/â`+`c/p/t`, không `nh/ch`) ⇒ `sawc→săc`, `sawcs→sắc`, `uwt→ưt` (đổi có chủ ý); `status`/`git` nguyên văn. `accept-shell-tmux.sh` 10/10.
(3) Đo: Rust **69+8+5+2** PASS · clippy 0 · release 0 · Python 90 OK · matrix **9/9 lane** exit 0 (`harm=0`) · QG xanh fmt/clippy/test (đã fmt crate CŨ `src/`) — đỏ còn lại chỉ là "tệp chưa commit" ở lượt trước commit.
(4) Firefox THẬT vẫn KHÔNG ĐO ĐƯỢC trong Xvfb (WM vẫn `DOM keys=0`, lỗi môi trường); WebKit `tiee→tieê` (N01) chưa sửa.

CHƯA ĐO (cần mắt/tay Hà): gõ thật `tieengs`/`mowis` ở Files + Telegram web sau khi cài bản mới; N05 key→pixel; TUI terminal.
VIỆC KẾ: (1) Hà gõ thật ⇒ sai thì lấy `engine-trace.log` + `surrounding-event`; (2) bảng khác biệt dataset chờ Hà tích; (3) TUI + bỏ cấm Backspace chờ Hà chốt; (4) Firefox thật khi có WM/máy thật.
Nền: KHÔNG. Luật: nhãn `zkey`, CẤM `cd` trần; env phiên có `XDG_*=…/.opencode-acc8/*` + `ZKEY_MODE=off` ⇒ chạy tay/cài phải `env -u` các biến ấy.
