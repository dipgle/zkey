# zkey — bộ gõ tiếng Việt cho Ubuntu

- Gốc dự án: `/mnt/data/projects/zkey`; chỉ ghi trong cây này.
- Đọc `README.md`, `TODO.md`, `memory/active-context.md` trước khi tiếp tục.
- Mục tiêu: gõ tiếng Việt ít trễ, không mất/nhân chữ; mọi tuyên bố về độ mượt phải có phép đo trên ứng dụng thật.
- Bản đầu: lõi Telex Rust không phụ thuộc ngoài + adapter IBus Python/GObject. Không can thiệp `/dev/input`, không giả phím Backspace, không đọc clipboard.
- Không ghi nội dung gõ vào log. Password/PIN phải đi thẳng khi ứng dụng khai báo đúng input purpose.
- Không đổi bộ gõ hệ thống, restart IBus hoặc cài vào thư mục ngoài dự án trong phiên này.
- Tra `scripts/impact.py` trước sửa mã; bản đồ trích từ module Rust và import Python, thiếu nút thì chạy toàn bộ kiểm.
- Kiểm: `cargo test --offline`; `cargo clippy --offline --all-targets -- -D warnings`; `cargo build --offline --release`; `/usr/bin/python3 -m unittest discover -s tests -v`.
- Phép kiểm lõi/protocol không thay thế nghiệm thu desktop; ghi rõ CHƯA ĐO ĐƯỢC nếu thiếu GUI hoặc session bus.
- Cấu hình nằm trong TOML; thay đổi qua màn thiết lập native, kiểm hợp lệ trước lưu. Bí mật và nội dung gõ không lưu.
- Kết thúc mạch: cập nhật `TODO.md`, `memory/active-context.md`, `logs/devlog.md`; không tuyên bố sản phẩm xong khi chưa nghiệm thu gõ thật.
