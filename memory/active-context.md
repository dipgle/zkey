# zkey/core — native (21/11 sáng)

21/11: Hà báo «gõ cách rồi xoá, thêm dấu vẫn không nhận» ⇒ **gốc: engine TRÊN MÁY là bản cài 19/11** (thiếu `Composer::seed`). Đã cài lại build 20/11 (`disable`+`enable --trace`, mã 0/0): binary cài = build `dbb97c16`, engine PID 2197899, `gsettings sources` = `[('ibus','zkey-native')]`.
Cổng **đo trên engine ĐÃ CÀI** (`native/tests/accept_installed_gtk3.py`, kịch bản của Hà): RED `săcs` trước khi cài → GREEN `sắc` sau; `scripts/accept-installed.sh` **4/4 GATE 0**.
Sự cố cùng lượt: user manager giữ `XDG_*HOME`/`IBUS_ADDRESS(_FILE)` trỏ `.tmp` ⇒ unit IBus GNOME nghe socket tạm (`ibus_write_address: pf != NULL`), file bus đứng PID cũ. Đã dọn + restart unit; **cổng canh mới** trong `scripts/accept-native-matrix.sh` (so env + `IBUS_DAEMON_PID` trước/sau, lane `ONLY=self-test-leak` chứng minh ĐỎ được).

Lượt 20/11 (vẫn đúng): ma trận native **9/9 GATE 0** (`scripts/accept-native-matrix.sh`), `accept-xvfb.sh` GATE_EXIT=0, sửa cổng ptyxis (so sánh `= as` bị Telex ở dòng lệnh) — `scripts/accept-latency.sh` cho N05 toolkit: xkb p50 1,95 / zkey 1,93–1,94 ms (chưa phải pixel).

Mã sản phẩm không đổi lượt này (chỉ cài lại + mở rộng cổng); Rust không chạy lại; Python `unittest` OK.

VIỆC KẾ: (1) Hà thử lại `săc`+space+BS+`s` (và Firefox thật); (2) Files «từ đầu tiên» — chờ Hà duyệt bộ đệm riêng; (3) TUI terminal + bỏ cấm Backspace — chờ Hà; (4) N05 thiếu key→pixel + desktop.

Nền: KHÔNG. Luật: nhãn `zkey`, CẤM `cd` trần; env phiên có `ZKEY_MODE=off` + `XDG_CONFIG_HOME` của opencode ⇒ chạy tay cổng/gsettings phải `env -u`. Hòm thư huba phiên: `/tmp/claude-1000/-mnt-data-projects/ses_e06f09837ffedkvJJi0ZBam657/scratchpad/huba-run.txt`.
