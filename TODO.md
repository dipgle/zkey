# Việc mở

- [x] **Ghép đường kế nhiệm (15/11 05:55):** resolver mới đo đúng `/mnt/data/projects/zkey`, paths15/Linux7 tests đạt. Cổng host mã0, acc6 pane%8 CLI_PID120194 CLI_LIVE=1. Log `.tmp/open-successor-0555.log`; brief `.tmp/brief-core-ke-nhiem-20261115-0555.md`. Đây là mở phiên, chưa nghiệm thu sản phẩm.

- [x] P0-001 vế an toàn (15/11 09:00): terminal VTE thật — phím đi nguyên, `read -s` không lộ/không biến đổi; cổng `scripts/accept-terminal.py` có đối chứng 2 chiều.
- [x] Tiếng Việt trên dòng lệnh bash: plugin readline `shell/zkey.bash` + `zkey-line`; nghiệm thu VTE thật + đối chứng 2 chiều (15/11 10:00).
- [ ] Terminal còn thiếu: vim/TUI, zsh, SSH (plugin máy xa), ptyxis app thật, tmux; câu tiếng Anh trong nháy bị đổi ở âm tiết hợp lệ.
- [x] Plugin đã cài vào ~/.bashrc (15/11, `scripts/install-shell.sh`); ptyxis thật + ~/.bashrc XANH 2/2, đối chứng ĐỎ.
- [x] `zkey --run`: ứng dụng và dịch vụ kích hoạt dùng hai XDG_RUNTIME_DIR khác nhau ⇒ ptyxis thoát. Sửa `runtime.py`: launcher không IBus 4/5 chết → 3/3 sống.
- [ ] `zkey --run ptyxis` với IBus: còn chết 1/3 (trước sửa 4/4). Chưa tìm gốc phần dính IBus.
- [ ] Bước ô mật khẩu GTK3 trong lượt gộp đỏ 1/~12 (phím mất) khi còn cửa sổ GTK4 trên màn không WM. Tìm gốc.
- [ ] **P0-001 CHẶN PHÁT HÀNH:** thay đường giữ từ trong preedit; bảo đảm terminal tắt echo không lộ/biến đổi mật khẩu. InputPurpose PASSWORD/PIN chưa đủ. Hợp đồng và phép nghiệm thu: `docs/input-contract.md`.
- [ ] Thăm dò đường sửa ký tự đã commit theo từng frontend; VTE cài trên máy không hỗ trợ surrounding-text rewrite. Chưa quyết định backend terminal.
- [x] Viết đường commit từng phím + sửa suffix theo incoming surrounding/caret/selection. Python 33/33; chưa nghiệm thu UI bản mới.
- [x] Gõ thật XANH 15/11 08:00 trên Xvfb riêng (`scripts/accept-xvfb.sh`, 3/3): GTK4 Text Editor + GTK3 (gõ dồn 0 ms, ô mật khẩu đi thẳng). Desktop thật cần hộp thoại RemoteDesktop mỗi lần ⇒ không dùng để tự động.
- [x] Sửa xáo chữ khi gõ nhanh (`tieseng`): engine commit mọi phím in được + ghép bù khi app xác nhận. RED→GREEN trên bài GTK3 thật; Python 44/44.
- [x] **AN NINH (15/11 15:40, huba báo):** plugin bash viết lại lệnh do MÁY gõ (`git reset`→`git rết` trong `--disallowedTools`, `ROOT`→`RÔT`, `doc_max`→`doc_mã`). Sửa `shell/zkey.bash`: hàng đợi phím còn byte (`read -t 0`) ⇒ cả dòng nguyên văn; từ sau ký tự định danh và từ toàn hoa giữ nguyên. Cổng `scripts/accept-shell-tmux.sh` RED→GREEN 5/5, đối chứng bỏ từng chốt ĐỎ đúng ca; VTE plugin/ptyxis vẫn XANH.
- [ ] Plugin bash: từ gõ xong rồi mới thêm `_`/`=` phía sau (`mas_x`) vẫn đã bị đổi; người gõ nhanh hơn thời gian xử lý (máy chậm) ⇒ dòng thành nguyên văn (an toàn, kém tiện).
- [x] **Gõ dồn có Backspace/Enter xen giữa (15/11 16:00):** gốc = module IBus GTK3/GTK4 chế độ bất đồng bộ đẩy phím engine không nhận ra CUỐI hàng sự kiện (`gdk_event_put`), còn commit vào ngay. `runtime.py` đặt `IBUS_ENABLE_SYNC_MODE=1` cho ứng dụng do zkey mở. GTK3 0/30 → 30/30; đối chứng `ZKEY_CLIENT_SYNC_MODE=0` ĐỎ 0/30; accept-xvfb 2/2 XANH 6/6 bài. Chi phí: phím→chữ trung vị 4 → 6 ms (tối đa 8.3).
- [ ] Gõ dồn + phím native: CHƯA đo trên GTK4 (Text Editor) và app không qua `zkey --run` (bộ gõ hệ thống, khi cài — env của người dùng không có cờ sync). Engine bị treo ⇒ app chờ phản hồi từng phím (chưa đo hành vi).
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
