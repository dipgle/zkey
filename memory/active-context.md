# zkey/core — native (20/11 tối)

ĐÃ ĐO THẬT: quota `/tmp` gỡ ⇒ mọi cổng GUI chạy lại.
(1) `bash scripts/accept-native-matrix.sh` **9/9 lane GATE 0**; GTK3+GTK4 thật XTest: `săc+space+BS+s → sắc`, đối chứng `săc space s → "săc s"` ⇒ NỢ «seed» đóng phần GUI. Ma trận nay ở repo.
(2) `scripts/accept-xvfb.sh` GATE_EXIT=0 (editor GTK4, VTE ×2, ptyxis, settings, shell-tmux 9/9); «MÁY NGUYÊN» portal active, mount 1→1.
(3) Sửa lỗi cổng `accept-ptyxis.py`: so sánh `= as` gõ ở dòng lệnh bị `ZKEY_MODE=all` Telex ⇒ DIFF oan; nay ở tệp `.tmp/ptyxis-secret-check.sh`; đối chứng `ZKEY_PTYXIS_EXPECT_SECRET=ax` ⇒ GATE 1.
(4) Firefox thật: `ZKEY_FF_WM` + twm/openbox trong `.tmp/tools`; phím tới X window mà DOM `keys=0` (`NO_E10S`/`testmode`/`GFX` cũng 0) ⇒ KHÔNG ĐO ĐƯỢC trên Xvfb+WM tối thiểu; chờ Hà gõ `tieengs` bằng mắt.

Mã sản phẩm không đổi; `cargo` không chạy lại; Python `unittest` OK.

VIỆC KẾ: (1) Hà gõ Firefox thật; (2) Files «từ đầu tiên» — chờ Hà duyệt bộ đệm riêng; (3) TUI terminal + bỏ cấm Backspace — chờ Hà; (4) N05: có A/B toolkit (`scripts/accept-latency.sh`: xkb p50 1,95 / zkey 1,93–1,94 ms; cấy chậm 12 ms tách được) — thiếu key→pixel + desktop.

Nền: KHÔNG. Nháp `accept_seed_dbus.py` **đã xoá** (huba). Env phiên có `ZKEY_MODE=off` ⇒ chạy tay cổng shell phải `env -u ZKEY_MODE`. Luật: nhãn `zkey`, CẤM `cd` trần.
Đã đẩy: huba chạy `git push` (e5c1f29) — verify `HEAD==origin/master`. Hòm thư phiên = `/tmp/claude-1000/-mnt-data-projects/ses_e06f09837ffedkvJJi0ZBam657/scratchpad/huba-run.txt` (hubd đọc đúng).
