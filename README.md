# zkey

Bộ gõ Telex cho Ubuntu, lõi Rust và adapter IBus Python/GObject. Đường mới gửi chữ vào ứng dụng theo từng phím; khi thêm dấu, sửa phần chữ vừa gõ bằng surrounding-text đã được ứng dụng xác nhận.

Gõ thật đã XANH trên GNOME Text Editor (GTK4) và ô nhập GTK3 trong màn X ảo riêng (15/11, 3/3 lượt, có vết engine private): gõ từng phím, gõ dồn, ô mật khẩu đi thẳng. Terminal (VTE thật): mật khẩu `read -s` không lộ/không đổi; gõ tiếng Việt trên dòng lệnh bash qua plugin `shell/zkey.bash`. CHƯA nghiệm thu: desktop Wayland-native, Chrome/Electron, vim/TUI, SSH, zsh. Chưa có bằng chứng mượt hơn các bộ gõ khác.

**Phạm vi:** chỉ biến đổi Telex ở client hỗ trợ surrounding-text và có cập nhật xác nhận. Client thiếu khả năng này, PASSWORD/PIN/TERMINAL và private hints nhận phím nguyên trạng. Đây chưa phải bộ gõ Telex cho toàn bộ terminal hoặc toàn hệ thống. Không dùng bản thử cho bí mật thật khi chưa nghiệm thu đúng ứng dụng. Xem [hợp đồng nhập liệu và bảo mật](docs/input-contract.md).

Đường dự án thật: `/mnt/data/projects/zkey` (`~/projects/zkey`). `/projects` không có tại thời điểm khảo sát 2026-11-14.

Đọc `docs/design.md` và `TODO.md` để xem phạm vi và việc còn thiếu.

## Bản thử hiện có

- Telex: `aa/aw/ee/oo/ow/uw/dd`, `uo+w`, `ua+w`, dấu `s/f/r/x/j`; `z` bỏ dấu thanh.
- Gõ lặp phím dấu để hoàn nguyên; Escape trả chuỗi phím kể từ lần Backspace gần nhất.
- Backspace do ứng dụng xoá ký tự theo cách gốc; gõ tiếp vẫn giữ dấu. Chọn cách đặt dấu hiện đại/truyền thống.
- Không giữ từ trong preedit. Engine tự commit mọi phím in được (chữ, dấu cách, dấu câu) để giữ đúng thứ tự khi gõ nhanh; chỉ phím không in được (Backspace, Enter, mũi tên) đi native. Chỉ xoá phần chữ do chính engine commit khi ảnh chụp của ứng dụng cho thấy nguyên văn phần đó ngay trước caret, không có vùng chọn và đứng sau ranh giới từ; gõ quá nhanh thì ghép bù khi ứng dụng xác nhận. Đổi focus/phím tắt không commit lại chữ đã nhận.
- `bash scripts/accept-xvfb.sh` chạy nghiệm thu gõ thật (GTK4 Text Editor + GTK3) trên màn X ảo riêng, không đụng desktop.
- `bin/zkey --run` mở Text Editor trong phiên IBus riêng; `--run <ứng dụng> [tham số]` chạy ứng dụng chỉ định. Không đổi fcitx5/IBus toàn hệ thống. Tệp `zkey.desktop` mới nằm trong repo, chưa cài menu hệ thống.
- Cấu hình TOML, màn thiết lập GTK3 và gói cài user-local được dựng thử trong `.tmp/stage`.

Chưa có VNI, tự kiểm chính tả, phục hồi từ trước lần đổi focus hoặc kiểm chứng toàn bộ biến thể Telex. Escape sau khi bắt đầu từ chuyển từ đó sang nguyên trạng (hữu ích khi nhập tiếng Anh/đường dẫn). Chưa thử màn thiết lập bằng mắt. Chưa nên thay bộ gõ đang dùng cho toàn hệ thống.

## Dành cho phát triển

Cần Rust, Python hệ thống có `gi`, typelib IBus 1.0 và GTK 3. Không cần npm hoặc gói Rust từ mạng.

```bash
cargo build --offline --release
cargo test --offline
cargo clippy --offline --all-targets -- -D warnings
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/impact.py --record
/usr/bin/python3 scripts/audit_measurements.py
```

`bin/zkey` là launcher Python của engine; `--settings` mở màn thiết lập native khi có GUI. `scripts/stage.py` chỉ tạo tệp trong `.tmp/stage`; chưa cài vào `~/.local`, chưa bật bộ gõ trên GNOME. Tệp component mẫu được sinh cùng launcher và thư viện để tránh lệch đường dẫn.

`scripts/probe-host.sh` là phép thăm dò protocol trên D-Bus/IBus riêng, không thay phiên desktop; kết quả phải đọc đến `GATE_EXIT` trong `.tmp/ibus-probe.log`. Đã xếp qua huba do sandbox không cho bind socket.

Kết quả đã đo và phần chưa đo: [docs/verification.md](docs/verification.md).

## Terminal (bash)

Bộ gõ không sửa được chữ đã gửi vào terminal và không biết lúc nào terminal đang hỏi mật khẩu, nên trong terminal phím đi nguyên trạng. Tiếng Việt trên dòng lệnh do readline của bash làm: chữ hiện ngay, dấu sửa ngay trong dòng; `sudo`, `read -s`, ssh không đi qua đây.

```bash
cargo build --offline --release
echo 'source /mnt/data/projects/zkey/shell/zkey.bash' >> ~/.bashrc   # rồi mở terminal mới
```

- Mặc định chỉ áp trong dấu nháy (`git commit -m "..."`, `echo "..."`); lệnh, cờ, đường dẫn giữ nguyên. **Alt+Z** đổi: trong nháy → mọi từ → tắt. `zkey-status` xem chế độ/lỗi.
- Lệnh do **máy** gõ (tmux `send-keys`, trình mở phiên, tự động hoá — nhiều phím đã xếp hàng khi xử lý một phím) giữ **nguyên văn cả dòng** tới khi dòng được làm trống (Enter, Ctrl+U). Từ dính định danh/đường dẫn/biến (`doc_max`, `$HOME`, `a/b`, `x=y`) và từ TOÀN HOA (`ROOT`, `API`) không đổi — đổi lại, tiếng Việt gõ toàn hoa cũng giữ nguyên. Kiểm: `bash scripts/accept-shell-tmux.sh`.
- Kết quả không phải âm tiết tiếng Việt thì giữ nguyên phím (`status`, `add`, `class`). Câu tiếng Anh trong nháy vẫn có thể đổi ở âm tiết hợp lệ (`us` → `ú`): tắt bằng Alt+Z.
- Đo: ~330 µs/phím cho hàm plugin + lõi (`scripts/bench-shell.sh`, chưa gồm vẽ lại terminal). Chưa có: vim/TUI, zsh, SSH (cần plugin ở máy xa).

## Giấy phép

`AGPL-3.0-or-later` — xem [LICENSE](LICENSE) và [NOTICE.md](NOTICE.md). Dùng lại bất kỳ phần mã nào (kể cả chạy làm dịch vụ mạng) thì **phải công khai toàn bộ mã nguồn dự án dùng lại theo cùng giấy phép** và **ghi rõ nguồn**: `Dựa trên zkey — https://github.com/dipgle/zkey (AGPL-3.0-or-later)`.
