# zkey/core — native (20/11 tối)

ĐÃ ĐO THẬT lượt này: quota `/tmp` đã được gỡ ⇒ mọi cổng GUI chạy lại được.
(1) ma trận native `bash .tmp/accept-native-matrix.sh` **8/8 lane GATE 0** (log `.tmp/matrix-full-20261120-1800.log`), trong đó GTK3+GTK4 thật XTest: `săc+space+BS+s → sắc`, đối chứng `săc space s → "săc s"` ⇒ **NỢ «seed» đóng phần GUI**.
(2) `scripts/accept-xvfb.sh` **GATE_EXIT=0** (editor GTK4, VTE ×2, ptyxis, settings, shell-tmux 9/9), harm gate «MÁY NGUYÊN» portal active, mount 1→1.
(3) Sửa lỗi cổng: `accept-ptyxis.py` gõ `[ "$p" = as ]` ở dòng lệnh ⇒ `ZKEY_MODE=all` Telex thành `= á` ⇒ DIFF oan. Nay câu so sánh ở tệp `bash .tmp/ptyxis-secret-check.sh`; đối chứng `ZKEY_PTYXIS_EXPECT_SECRET=ax` ⇒ ĐỎ (GATE 1), mặc định ⇒ PASS.
(4) Firefox thật: thêm `ZKEY_FF_WM` + tải twm/openbox vào `.tmp/tools`; phím tới X window (xev KeymapNotify, focus=child) nhưng DOM `keys=0`; `NO_E10S`, `testmode`, `GFX` đều 0 ⇒ **KHÔNG ĐO ĐƯỢC trên Xvfb+WM tối thiểu**, không phải lỗi zkey. Vẫn chờ Hà gõ `tieengs` bằng mắt.

Rust/Python không đổi mã sản phẩm; `cargo` không chạy lại lượt này (không sửa `native/src`). Python `unittest` = OK.

VIỆC KẾ: (1) Hà gõ Firefox thật; (2) Files «từ đầu tiên» — chờ Hà đồng ý bộ đệm riêng; (3) TUI terminal (b) + bỏ cấm Backspace — chờ Hà; (4) N05 chưa có A/B độ mượt (đo được ngay trên Xvfb: zkey vs `xkb:us::eng`).

Nền: KHÔNG. Nháp untracked `native/tests/accept_seed_dbus.py` (rm bị chặn) — xoá tay.
Môi trường phiên: `ZKEY_MODE=off` có sẵn trong env ⇒ chạy tay cổng shell phải `env -u ZKEY_MODE`. Luật: nhãn `zkey`, CẤM `cd` trần.
