# zkey/core — native (23/11)

ĐÃ CÀI (engine = build `7013c097…`, `native-ime.py` 0/0):
(1) **Bộ đệm từ đầu tiên** (Hà duyệt 22/11, `session.rs`): `published`/`reports_caret`/`blind` — `Reset` sau commit chỉ xoá từ khi app đã từng gửi lại snapshot; ngữ cảnh câm giữ bộ đệm riêng và ghép tiếp (`tieengs→tiếng`, `mowis→mới`); snapshot sai `owns()`/FocusOut/đổi ContentType/phím không in ⇒ xoá; chưa từng có snapshot ⇒ không đoán. Test RED→GREEN 4+3; `accept_silent_context.py` (2 chiều) — `accept-installed.sh` 5/5.
(2) **Terminal `sawc`:** tách `valid_syllable` (hình thái) ↔ `spell_ok` (chính tả Hà) ⇒ `sawc→săc`, `sawcs→sắc`, `uwt→ưt` (cố ý); `status`/`git` nguyên. tmux 10/10.
(3) Đo 23/11: Rust 69+8+5+2 · clippy/release 0 · Python 90 · matrix 9/9 · `accept-xvfb` 0 · QG xanh.
(4) **Cổng:** `accept-editor.py` retry AT-SPI 20 lượt → `NOT_MEASURABLE` exit 2 (sai thật = 1); `accept-xvfb.sh` thôi đếm key-state khi 2. Đối chứng: 0 / 2 (cấy lỗi) / 1 (`sync=0`).
(5) **Tên phiên + `.inbox`** là việc huba: phiếu `.tmp/phieu-huba-dat-ten-20261123.md` đã chuyển phiên huba `ses_df863a01…`; zkey không sửa.

CHƯA ĐO (cần Hà): `tieengs`/`mowis` ở Files + Telegram web; N05 key→pixel; TUI.
VIỆC KẾ: (1) Hà gõ thật; (2) Firefox thật khi có WM; (3) TUI + bỏ cấm Backspace chờ Hà; (4) dataset chờ Hà tích.
Nền: KHÔNG. Luật: nhãn `zkey`, CẤM `cd` trần; env phiên `XDG_*=…/.opencode-acc8/*` + `ZKEY_MODE=off` ⇒ `env -u`.
