# zkey/core — native (21/11 chiều)

ĐÃ CÀI + ĐO trên engine ĐÃ CÀI (21/11):
(1) **Nhận dấu cho từ có sẵn** (Hà chốt CÓ): phím `s f r x j z` áp vào từ ngay trước con trỏ, kể cả chữ dán; chốt an toàn (chỉ phím dấu, không bóng chọn, ≤ `max_keys`, chỉ dãy chữ cái, mật khẩu/terminal bypass, Ctrl/Escape đóng băng chỉ thêm). `scripts/accept-installed.sh` **4/4 GATE 0**: `laj nhi`+4×BS+`s`→`lá`, `lạ`(dán)+`s`→`lá`, `săc`+space+BS+`s`→`sắc`, đối chứng `săc s`.
(2) **Chính tả 5 nguyên âm** (`compose.rs` `valid_syllable`): `ư/ô/ơ/ă/â`+`m/n` luôn đúng (`ưn, ưm, ôn, ôm, ăn, ăm`); +`c/p/t` phải có dấu (`ứt, ộc, ắt`; `ưt, ôc, ăt` sai); +`nh/ch` luôn sai (`ănh, ânh`); `ng` giữ đúng (`ông, măng, cưng, vâng`). Rust **60+7+5+2 PASS**, clippy 0, release 0.
(3) **Sự cố env (đã sửa):** activation env bus phiên giữ `IBUS_ADDRESS=` rỗng ⇒ app do bus sinh ra (Text Editor) **không ra chữ**. `native-ime.py` nay gỡ `IBUS_ADDRESS(_FILE)` khỏi user manager trước restart + SET địa chỉ mới vào activation env sau restart. Kiểm: dịch vụ kích hoạt mới có `IBUS_ADDRESS` = socket sống. **Text Editor cũ phải đóng hẳn rồi mở lại** (chưa xác nhận từ Hà).
(4) **Dataset chính tả:** `vietnameselanguage/syllable` (7.884, `.tmp/vi-syllables-raw.txt`) lệch Hà hai chiều (`ưm` thiếu, `ưt` có) ⇒ không làm chuẩn; chỉ sinh bảng khác biệt cho Hà tích.

VIỆC KẾ: (1) Hà mở lại Text Editor ⇒ đo env tiến trình mới, xác nhận ra chữ; (2) bảng khác biệt dataset vs quy tắc cho Hà tích; (3) Firefox thật bằng mắt; (4) «từ đầu tiên» Files — chờ Hà duyệt bộ đệm riêng; (5) TUI terminal + bỏ cấm Backspace — chờ Hà.

Nền: KHÔNG. Hòm thư huba phiên: `/tmp/claude-1000/-mnt-data-projects/ses_e06f09837ffedkvJJi0ZBam657/scratchpad/huba-run.txt`. Luật: nhãn `zkey`, CẤM `cd` trần; env phiên có `ZKEY_MODE=off` + `XDG_CONFIG_HOME` của opencode ⇒ chạy tay phải `env -u`.
