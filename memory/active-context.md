# zkey/core — native (19/11 sáng, phiên claude acc3 → kế nhiệm)

XONG & ĐÃ CÀI (commit eb00710, 9769fc6): bản Rust tự nói D-Bus/IBus/Notify, binary chỉ nối libc+libgcc_s; thiết lập `--show/--set`; cài thật qua `python3 scripts/native-ime.py enable --trace`. Gõ OK trong Text Editor. Telex truyền thống: `cuss→cus`, `ww→w`.
ĐO: cargo test 59, clippy 0, Python 90+6, ma trận 8 lane Xvfb riêng GATE 0 (`bash .tmp/accept-native-matrix.sh`), harm gate mount 1→1.

CHƯA ĐƯỢC: (1) Firefox: engine xử lý 7/7 phím nhưng chữ hiện sai, gốc chưa rõ — Hà gõ `tieengs` ở ô tìm kiếm, báo chữ hiện ra, rồi đối chiếu `~/.local/state/zkey-native-ime/engine-trace.log` (dòng `edit sent remove= insert_chars=`). (2) tmux/ptyxis: bypass TERMINAL theo hợp đồng; plugin bash còn lõi cũ. (3) N01 WebKit đỏ.
CHỜ HÀ: bỏ cấm Backspace qua IBus cho ô không surrounding? (cấm do phiên đầu tự ghi, không phải yêu cầu Hà). Không dùng preedit.
HUBA (ngoài zkey): bản giao 4 mục nhãn/focus/footer/Tele chờ Hà dán vào phiên huba (không có phiên sống).
LUẬT MỚI: CLAUDE.md «Nhãn dự án…»: nhãn = zkey cố định, CẤM `cd` trần (đo: cd trần đổi nhãn, subshell không).
Nền: KHÔNG CÓ (trace chẩn đoán đang bật trên máy).
