# zkey/core — native (20/11 chiều, phiên kế nhiệm 17:28)

ĐÃ LÀM (chưa commit lúc viết): gõ lại dấu sau khi xoá dấu cách — `session.rs` nhận lại từ vừa commit khi snapshot chứng minh đúng con trỏ/chuỗi/không chọn/độ dài; `Composer::seed`. Rust 69 PASS, clippy 0, release 0, fmt 0; Python 90. RED→GREEN có đối chứng.

Plugin bash: mặc định `ZKEY_MODE=all`; máy-gõ = có byte xếp hàng + 2 phím ≤ 8000 µs. `accept-shell-tmux.sh` 9/9 GATE 0 + đối chứng 2 chiều ĐỎ đúng ca.

🔴 CHẶN: `/tmp` hết quota user (5,9 G ở `/tmp/claude-1000`; còn 1,6 G mà ghi 2 MB vẫn EDQUOT) ⇒ Xvfb không tạo lock ⇒ MỌI cổng GUI KHÔNG ĐO ĐƯỢC. Hà chọn: đổi `CLAUDE_CODE_TMPDIR` hoặc duyệt dọn `/tmp/claude-1000`.

VIỆC KẾ: (1) chạy `accept_desktop.py` (kịch bản `săc`+space+BS+`s⇒sắc` đã viết) sau khi gỡ quota; (2) Firefox: chờ Hà gõ `tieengs`; (3) Files «từ đầu tiên» — chờ Hà đồng ý bộ đệm riêng; (4) TUI terminal (b) chưa làm.

Nền: KHÔNG. Luật: nhãn `zkey`, CẤM `cd` trần. Phiên cũ `4210` (pts/0) vẫn sống, cây chưa sạch nên KHÔNG đóng.
