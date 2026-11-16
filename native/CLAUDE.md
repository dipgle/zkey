# zkey native

- Bản viết mới Hà giao 16/11/2026: Rust + thư viện chuẩn; không dependencies Cargo, không nhập mã sản phẩm Python/lõi cũ.
- Chỉ dùng ABI/giao thức công khai của thư viện HỆ THỐNG Ubuntu; khai đầy đủ trong README. Không gọi bản này là không phụ thuộc hệ điều hành.
- Giữ bản cũ để đối chiếu; không cài, đổi nguồn nhập hoặc restart bộ gõ hệ thống.
- Mã Rust chỉ ghi log trạng thái/lỗi, không ghi phím hay surrounding text. Callback C không được unwind.
- Chạy cargo test/clippy/build --offline với --manifest-path native/Cargo.toml. Kiểm UI phải dùng màn/bus riêng, không dùng UI giả thay nghiệm thu.
- Mã thoát 2 = không đo được, không phải xanh. Giữ ca WebKit bỏ delete là lỗi phát hành cho tới khi có đường sửa thật.
