# zkey/core — native (20/11 tối)

ĐÃ ĐO THẬT lượt này: quota `/tmp` đã được gỡ ⇒ mọi cổng GUI chạy lại được.
(1) ma trận native `bash scripts/accept-native-matrix.sh` **9/9 lane GATE 0** (log `.tmp/matrix-versioned-20261120-2130.log`), trong đó GTK3+GTK4 thật XTest: `săc+space+BS+s → sắc`, đối chứng `săc space s → "săc s"` ⇒ **NỢ «seed» đóng phần GUI**; bản ma trận nay nằm trong repo (trước chỉ ở `.tmp`).
(2) `scripts/accept-xvfb.sh` **GATE_EXIT=0** (editor GTK4, VTE ×2, ptyxis, settings, shell-tmux 9/9), harm gate «MÁY NGUYÊN» portal active, mount 1→1.
(3) Sửa lỗi cổng: `accept-ptyxis.py` gõ `[ "$p" = as ]` ở dòng lệnh ⇒ `ZKEY_MODE=all` Telex thành `= á` ⇒ DIFF oan. Nay câu so sánh ở tệp `bash .tmp/ptyxis-secret-check.sh`; đối chứng `ZKEY_PTYXIS_EXPECT_SECRET=ax` ⇒ ĐỎ (GATE 1), mặc định ⇒ PASS.
(4) Firefox thật: thêm `ZKEY_FF_WM` + tải twm/openbox vào `.tmp/tools`; phím tới X window (xev KeymapNotify, focus=child) nhưng DOM `keys=0`; `NO_E10S`, `testmode`, `GFX` đều 0 ⇒ **KHÔNG ĐO ĐƯỢC trên Xvfb+WM tối thiểu**, không phải lỗi zkey. Vẫn chờ Hà gõ `tieengs` bằng mắt.

Rust/Python không đổi mã sản phẩm; `cargo` không chạy lại lượt này (không sửa `native/src`). Python `unittest` = OK.

VIỆC KẾ: (1) Hà gõ Firefox thật; (2) Files «từ đầu tiên» — chờ Hà đồng ý bộ đệm riêng; (3) TUI terminal (b) + bỏ cấm Backspace — chờ Hà; (4) N05: đã có A/B toolkit (`scripts/accept-latency.sh`: xkb p50 1,95 / zkey 1,93–1,94 ms, cấy chậm 12 ms tách được) — còn thiếu key→pixel + desktop thật.

Nền: KHÔNG. Nháp untracked `accept_seed_dbus.py`: **đã xoá** (huba chạy `rm`, 20/11 20:58).
Môi trường phiên: `ZKEY_MODE=off` có sẵn trong env ⇒ chạy tay cổng shell phải `env -u ZKEY_MODE`. Luật: nhãn `zkey`, CẤM `cd` trần.
Đã đẩy: huba chạy `git push origin master` (2503149..e5c1f29) — verify `HEAD==origin/master`; hòm thư phiên = `/tmp/claude-1000/-mnt-data-projects/ses_e06f09837ffedkvJJi0ZBam657/scratchpad/huba-run.txt` (hubd đọc đúng, đã thấy `runin_inbox_queued`).
