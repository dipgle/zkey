# Việc mở

- [x] **Ghép đường kế nhiệm (15/11 05:55):** resolver mới đo đúng `/mnt/data/projects/zkey`, paths15/Linux7 tests đạt. Cổng host mã0, acc6 pane%8 CLI_PID120194 CLI_LIVE=1. Log `.tmp/open-successor-0555.log`; brief `.tmp/brief-core-ke-nhiem-20261115-0555.md`. Đây là mở phiên, chưa nghiệm thu sản phẩm.

- [x] P0-001 vế an toàn (15/11 09:00): terminal VTE thật — phím đi nguyên, `read -s` không lộ/không biến đổi; cổng `scripts/accept-terminal.py` có đối chứng 2 chiều.
- [x] Tiếng Việt trên dòng lệnh bash: plugin readline `shell/zkey.bash` + `zkey-line`; nghiệm thu VTE thật + đối chứng 2 chiều (15/11 10:00).
- [ ] Terminal còn thiếu: vim/TUI, zsh, SSH (plugin máy xa), ptyxis app thật, tmux; câu tiếng Anh trong nháy bị đổi ở âm tiết hợp lệ.
- [ ] Cài plugin vào ~/.bashrc khi chủ dự án cho phép ghi ngoài repo.
- [ ] **P0-001 CHẶN PHÁT HÀNH:** thay đường giữ từ trong preedit; bảo đảm terminal tắt echo không lộ/biến đổi mật khẩu. InputPurpose PASSWORD/PIN chưa đủ. Hợp đồng và phép nghiệm thu: `docs/input-contract.md`.
- [ ] Thăm dò đường sửa ký tự đã commit theo từng frontend; VTE cài trên máy không hỗ trợ surrounding-text rewrite. Chưa quyết định backend terminal.
- [x] Viết đường commit từng phím + sửa suffix theo incoming surrounding/caret/selection. Python 33/33; chưa nghiệm thu UI bản mới.
- [x] Gõ thật XANH 15/11 08:00 trên Xvfb riêng (`scripts/accept-xvfb.sh`, 3/3): GTK4 Text Editor + GTK3 (gõ dồn 0 ms, ô mật khẩu đi thẳng). Desktop thật cần hộp thoại RemoteDesktop mỗi lần ⇒ không dùng để tự động.
- [x] Sửa xáo chữ khi gõ nhanh (`tieseng`): engine commit mọi phím in được + ghép bù khi app xác nhận. RED→GREEN trên bài GTK3 thật; Python 44/44.
- [ ] Gõ dồn có Backspace/Enter xen giữa: phím native vẫn có thể bị xếp sau commit; chưa có bài đo.
- [ ] Nghiệm thu trên desktop Wayland-native (ngoài Xwayland) và Chrome/Electron; cần đường nhập phím không qua hộp thoại.
- [x] Giảm rủi ro P0 tại handler: bypass TERMINAL; gửi preedit rỗng khi vào protected context/reset. RED→GREEN; 27/27 Python, chỉ transport sink. Chưa nghiệm thu UI, chưa đóng P0.

- [x] Lõi Telex thử nghiệm; 7 test Rust, gồm các hàng dấu/chữ hoa, ua/uo, FFI và sửa Unicode.
- [x] Viết adapter IBus và test handler/state machine; chưa nghiệm thu protocol/desktop.
- [x] Cấu hình TOML + màn thiết lập native; mới kiểm config, chưa xem UI.
- [x] Gói user-local được stage trong repo; chưa cài/bật trên hệ thống.
- [x] Đo 100.000 mẫu core: p50 96 ns, p95 1.222 ns, p99 2.398 ns; không phải độ trễ màn hình.
- [x] Bản đồ import/module + trace unittest; selector fail-closed, có đối chứng ngược.
- [x] Quét lại 101 khẳng định trong 7 tệp (23:49); 0 hình dạng đáng ngờ mà bộ quét nhận diện; vẫn cần soát ngữ nghĩa.
- [x] Protocol host trên D-Bus riêng: 7 nhóm mã 0; `.tmp/ibus-probe.log`. Không thay nghiệm thu UI.
- [ ] Nghiệm thu gõ thật trên GTK, Chrome/Electron, terminal, Wayland/X11; kiểm mất/nhân chữ và đổi focus.
- [ ] Đo đối chiếu bộ gõ đang gây khó chịu và chuẩn Windows do chủ dự án cung cấp.
- [ ] Kiểm corpus Telex rộng hơn, kiểu gõ dấu muộn; xác định chính sách tiếng Anh và VNI.
- [ ] Nghiệm thu settings GTK, cài/gỡ user-local và gói Ubuntu. Hoàn thiện audit thay cấu hình trước phát hành.
