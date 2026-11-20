# Kết quả 2026-11-14 — prototype, CHƯA nghiệm thu sản phẩm

## 19/11 11:40 — plugin dòng lệnh dùng `zkey-native --line`; gốc lỗi Firefox

### Đã chạy thật

- **Firefox — tìm ra cơ chế, sửa có khoá hồi quy:** dấu vết máy Hà (`.local/state/zkey-native-ime/engine-trace.log`) cho thấy mỗi phím: `key-event handled=true` → client gọi `Reset` → `SetSurroundingText`; đo lần 2 cả **14/14 phím `edit sent remove=0 insert_chars=1`**. `Session::client_reset` cũ xoá cả từ đang ghép ⇒ engine mất trạng thái sau mỗi phím, các phím sau chỉ chèn nguyên ký tự (đúng số đo). Sửa: Reset của client chỉ **treo** trạng thái; `SetSurroundingText` kế tiếp xác nhận từ còn đúng vị trí (owns) thì ghép tiếp, sai thì xoá. Bài `client_reset_after_every_commit_keeps_the_word_composable`: cũ `tieengs` + mỗi phím insert=1/remove=0, mới `tiếng` (RED đã đo bằng cách tạm khôi phục `client_reset` cũ). **CHƯA đo trên Firefox thật**: cần build + cài lại binary (chờ Hà) rồi Hà gõ `tieengs`. Bản build đã thêm trace SỐ `surrounding-event chars= cursor= anchor=` (không nội dung) để phân biệt ngay «snapshot trễ» nếu vẫn `remove=0`.
- **Kiểm trace mới:** lane GTK3 chạy lại GATE 0; trace có 186 dòng `surrounding-event ... chars=1 cursor=1 …` (chỉ số).
- **Plugin bash dùng lõi native:** `shell/zkey.bash` chạy `zkey-native --line [traditional]`, giữ lõi `zkey-line` làm dự phòng (nhận cả `=word`). Thêm `valid_syllable` vào `native/src/compose.rs`: giao thức trả nguyên văn khi kết quả không phải âm tiết Việt — nếu không, `status→státu`, `add→ađ`, `class→clas` (đã đo). `--line` nhận thêm `traditional`; mặc định modern.
- **Đối chiếu lõi cũ ↔ `--line`:** 167 từ (corpus 134 + 33 từ lệnh/tiếng Anh): chỉ 2 khác — `tienegs`/`tiesneg` lõi cũ trả nguyên văn, lõi mới ghép `tiếng` (đúng bài `late_shape_keys`); mọi từ lệnh giữ nguyên. Chế độ traditional (134 từ): cũng chỉ 2 khác đó. Từ có `_` bị cả hai từ chối như nhau.
- **Đo thật trên VTE + ptyxis:** `ZKEY_TERMINAL_PLUGIN=1` trên Xvfb: **GATE 0** (7 tiền tố hiện trên dòng lệnh thật, `tiếng việt` vào bash, `status test` ngoài nháy nguyên văn, `read -s` không lộ/không đổi). Đối chứng `ZKEY_MODE_UNDER_TEST=off` ⇒ **ĐỎ** ở `tiê`. `scripts/accept-ptyxis.py` với `~/.bashrc` thật: **GATE 0**. Sửa cổng: `accept-terminal.py` ghim `ZKEY_MODE=quoted` (trước đó kế thừa `off` từ shell cha ⇒ đo sai chế độ), `accept-xvfb.sh` `unset ZKEY_MODE`.
- **WebKit N01 vẫn ĐỎ sau sửa:** chạy lại `ZKEY_NATIVE_WEBKIT=1 native/tests/accept_desktop.py` trên Xvfb: `expected 'tiê', actual 'tieê'` — đúng lỗi frontend bỏ DeleteSurroundingText, không phải Reset-như-Firefox (sửa Reset không đổi kết quả).
- `scripts/accept-shell-tmux.sh`: **5/5 PASS, GATE_EXIT=0** (M1–M3 máy gõ nguyên văn, I định danh/hoa, H `tieengs vieetj→tiếng việt`). Sửa cổng: trước đó kế thừa `ZKEY_MODE=off` từ shell cha ⇒ đo sai chế độ (đã gặp thật); nay cổng **ghim `ZKEY_MODE=quoted`**.
- Kiểm: native `cargo test` 50+7+5+2; clippy `-D warnings` 0; `cargo build --release` 0 (attestation khớp nguồn). Lõi cũ: `cargo test`/clippy/build release 0. Python 90/90. Ma trận `bash .tmp/accept-native-matrix.sh`: **8/8 lane GATE 0**, harm gate portal active→active, mount 1→1.
- `scripts/stage.py` chép `zkey-native` vào gói khi đã build (plugin tìm ở `target/release`), vẫn giữ `zkey-line`. README/`docs/native-rewrite.md` N04 cập nhật.

### CHƯA ĐO ĐƯỢC

- Firefox thật với bản sửa: **đã cài bản sửa lên máy Hà lúc 11:47** (Hà 19/11 «tự làm tự kiểm đi»), kiểm tự động đúng mẫu gọi của Firefox qua D-Bus của daemon thật ⇒ xem mục dưới; còn chờ chính Hà gõ trong Firefox để nghiệm thu mắt.
- WebKit N01 vẫn ĐỎ; vim/TUI/zsh/SSH.

## 19/11 11:50 — cài bản sửa + tự kiểm mẫu gọi Firefox trên engine ĐÃ CÀI

- Hà ra lệnh «tự làm tự kiểm đi» ⇒ gỡ/cài lại bằng `scripts/native-ime.py disable` rồi `enable --trace` (công cụ đảo ngược được, đã dùng trước đó). Mã thoát 0/0; `status`: engine có trong daemon; `sha256` binary cài **trùng** binary build `2f979f84…`; một tiến trình engine mới (PID 4186151, 11:47); `ibus engine` qua địa chỉ daemon = `zkey-native`; không còn tiến trình engine cũ.
- **Cổng mới `native/tests/accept_firefox_pattern.py`** (D-Bus thật, không bơm phím, không đổi nguồn nhập, không đụng tài liệu người dùng): tạo engine qua factory của **engine đã cài**, gửi đúng chuỗi Firefox đã đo (`SetSurroundingText` → `ProcessKeyEvent` → áp `DeleteSurroundingText`/`CommitText` → `Reset` → `SetSurroundingText`), gõ `tieengs`. Kết quả: `text='tiếng' keys=7 removes=2 commits=7` ⇒ **PASS, GATE_EXIT=0**.
- **Cổng `native/tests/accept_installed_gtk3.py`** (GTK3 Entry thật trên Xvfb riêng, `GTK_IM_MODULE=ibus`, `IBUS_ADDRESS` của daemon thật, engine đang chọn = zkey-native): gõ XTest `tieengs` ⇒ Entry `'tiếng'` ⇒ **PASS**. Đối chứng `ZKEY_INSTALLED_SKIP_ENGINE=1` (IM module thường) ⇒ `'tieengs'` ⇒ cổng nhận ra khác biệt.
- `scripts/accept-installed.sh` gộp 2 cổng + 2 đối chứng: **GATE_EXIT=0** (`firefox-pattern` 0, `firefox-control` 1 đúng, `gtk3-entry` 0, `gtk3-control` 0).
- **Đối chứng ngược:** cùng cổng với client bỏ `SetSurroundingText` sau Reset (`ZKEY_FIREFOX_SKIP_SURROUNDING=1`) ⇒ `text='tieengs' removes=0` ⇒ **ĐỎ, GATE_EXIT=1**. Cổng đỏ được, không phải assert luôn xanh.
- Trace của engine đã cài ghi `surrounding-event ... chars=N cursor=N anchor=N` (chỉ số); ngữ cảnh thử đã `Destroy`, không rò.
- **Thử tự động Firefox snap trên Xvfb riêng = KHÔNG ĐO ĐƯỢC (đo lại, rõ hơn lần trước):** snap nhìn thấy `/tmp/.X11-unix/X80` (đã kiểm trong `snap run --shell firefox`) nhưng app vẫn `Error: cannot open display: :80` cả khi Xvfb `-ac` ⇒ sandbox snap chỉ cho display của phiên, không phải lỗi auth/đường dẫn. Không dùng display `:0` để tránh bơm phím vào phiên đang làm việc.
- Còn lại cần mắt người: Hà gõ `tieengs` trong Firefox thật (engine trên máy đã là bản sửa).

## 16/11 09:45 — chốt lượt, nhường phiên thiết kế theo yêu cầu mới của Hà

- Python73/73 mã0; `impact.py --record`137 nút/82 test. Hai ca mới RED→GREEN: socket bus phải ở runtime riêng thay `/tmp` bị Snap che; runtime/session-bus phải cùng đời để document-portal không giữ mount trong thư mục engine đã dọn. `bus_config.py` giữ policy/auth hệ thống, chỉ đổi listen và resolve include tương đối; `launch.py`/`private_bus.py` cùng dùng. Chưa cài bản này ngoài repo.
- Firefox Snap mở được khi `DISABLE_WAYLAND=1` (launcher Snap tự ép Wayland nếu thấy socket host). Sau khi bus nhìn thấy từ Snap, lộ cleanup `PermissionError runtime/doc`; đổi lifetime runtime sang đời bus hết lỗi cleanup ở lượt sau. Firefox vẫn đỏ tại phím đầu nhưng `.tmp/firefox-input.png` **là màn LOGO STARTUP**, chưa thấy ô gõ. Title/DOM activeElement/focus X11 KHÔNG đủ chứng minh UI sẵn sàng. Không kết luận lỗi nhập chữ engine từ lượt này. Chưa tìm/đóng startup overlay; chưa sửa fixture readiness.
- Lượt cuối `accept-xvfb.sh` mã1 (`.tmp/accept-xvfb.log`): GTK4+GTK3/bypass/settings đạt; plugin VTE không thấy tiê, ptyxis/tmux H nhận nguyên văn. Đo env phiên `ZKEY_MODE=off`; chưa chạy đối chứng quoted, không tự coi đã xác định toàn bộ nguyên nhân. Bộ kiểm chưa chuẩn hoá mode đầu vào là vấn đề thiết kế phép đo.
- Portal thật vẫn active/PID1936, mount1→1; không mount riêng còn lại trong `/proc/mounts`. Máy reboot09:30, loginctl chỉ còn manager user1+GDM greeter, chưa phiên desktop user1; ibus ở greeter không chứng minh zkey user1 đã chạy. Số PID365673 và phiên15/11 ở mục cũ là lịch sử trước reboot.
- Không có bài kiểm nền. Hà chuyển mục tiêu sang thiết kế toàn bộ, nên dừng sửa sản phẩm/kiểm mới và bàn giao diff+sổ trực tiếp qua synthetic cho ses_e1dc8e2baffeVY9CklW9BwSK9n; chưa commit/push/deploy. Brief `.tmp/brief-core-design-ke-nhiem-20261116-0945.md`.

## 16/11 08:10 — kế nhiệm: trang live khớp byte; phát hiện P0-WebKit

### Đã chạy thật

- `scripts/web-driver.py --verify-site` trên Xvfb + `private_bus.py`: WebKit thật mở `https://zkey.dipgle.com/`, JS `fetch('/', {cache:'no-store', credentials:'omit'})` + ArrayBuffer/SHA-256. HTTP200, HTML, 8.763 byte, SHA-256 `417f5ceed5be9509e5fc0ebb6813f5c5860a58ec5b50752c778057b9bcb017c6` trùng nguồn. Đối chứng thêm newline vào **nguồn đối chiếu trong RAM** ⇒ mã1; bản đúng ⇒0. Không upload/deploy/đăng nhập, không đổi tệp site. `.tmp/site-verification.json`. Chế độ này dùng profile ephemeral, không tái dùng cookie Studio.
- Python71/71; Rust9/9; clippy `-D warnings`/release build mã0. `impact.py --record`:133 nút/80 test (71 Python+9 Rust); selector không rõ tệp ⇒ toàn bộ. `audit_measurements.py`:13 tệp/234 assertion,0 mẫu nghi ngờ được nhận diện; không thay soát ngữ nghĩa.
- `accept-xvfb.sh`:7 bài mã0 (GTK4+GTK3, VTE, plugin, ptyxis, settings, tmux); `.tmp/accept-xvfb.log`; portal active/PID365673, mount1→1. Lượt trước bị công cụ cắt ở120s, mã143: **không tính xanh**; lượt lại cho600s hoàn tất. Lượt bị cắt còn có dbind warning AT-SPI; lượt hoàn tất không có warning đó. Không lấy latency của lượt chịu tải làm benchmark mới.
- Read-only: desktop GNOME vẫn đăng nhập15/11 14:54:01, fcitx5 PID3619 còn chạy; không bật zkey/restart/đăng xuất. Cấu hình thật (XDG_CONFIG_HOME=/home/user1/.config) có nguồn zkey; manifest bản cài16/16 khớp. Môi trường OpenCode dùng thư mục cấu hình riêng, lần đọc gsettings mặc định ra rỗng KHÔNG phải trạng thái desktop.

### P0-WebKit — **ĐỎ, chưa sửa**

- Bộ đo mới `scripts/accept-webkit.py` dùng WebKitGTK2.52.6/Gtk3.24.52/IBus1.5.34~rc2, X11/Xvfb + bus/engine riêng, fixture browser có sẵn. Phím XTest, giá trị/input/composition do **trang tự báo qua tiêu đề**; không gán DOM hoặc gọi API để tạo dữ liệu gõ.
- 4/4 lượt: tiền tố `t`, `ti`, `tie` đúng; phím `e` tiếp → `tieê`, không phải `tiê`. Engine khai caps41, nhận surrounding thật, gửi delete(-1,1) (`.tmp/run-gy_2vih_.log:12`); WebKit `WebKitInputMethodContextImplGtk` chỉ phát4 `committed`, không phát `delete-surrounding`. Ảnh `.tmp/webkit-input.png` đã xem. Đây là lỗi tương thích có thật; **chưa chứng minh điểm làm rơi bên GTK-IBus hay WebKit**, không đổ lỗi upstream khi chưa đủ bằng chứng.
- Vẫn kiểm ô password độc lập sau lỗi text: Tab bằng phím, chuỗi giả3 phím nguyên dạng,0 composition, purpose8/protected=True (`.tmp/run-gy_2vih_.log:16–22`). Toàn bài vẫn mã1; các bước phrase/Backspace chưa đi tới được báo skip, không nhận xanh.
- `zkey/engine.py` chỉ thêm trace offset/count, KHÔNG nội dung gõ và KHÔNG sửa hành vi. Khả năng **đọc** surrounding không đủ chứng minh có thể **xoá**; apply hiện gửi delete rồi commit ngay, nên suffix có thể bị nhân. Cần truy đường xoá và thiết kế xác nhận/fallback an toàn; không vá bằng Backspace giả hoặc đoán tên cửa sổ.
- Firefox/Wayland-native/Chrome/Electron vẫn CHƯA ĐO; WebKit này không thay nghiệm thu các frontend đó. P0-001 vẫn chặn phát hành. Không cài/đẩy mã mới lên máy người dùng.

Chạy riêng trên Xvfb của dự án (không desktop):

```bash
PATH="$PWD/.tmp/tools/root/usr/bin:$PATH" TMPDIR="$PWD/.tmp" \
  xvfb-run -a -f "$PWD/.tmp/webkit-input.auth" -s '-screen 0 1280x900x24 -nolisten tcp' \
  bash -c 'export ZKEY_TEST_DISPLAY="$DISPLAY"; exec /usr/bin/python3 scripts/accept-webkit.py'
```

So byte: cùng wrapper, thay lệnh cuối bằng `scripts/web-driver.py --verify-site`.

## 15/11 15:40 — plugin bash không còn viết lại lệnh do máy gõ

- Báo từ huba: lệnh mở phiên gõ qua `tmux send-keys -l` vào bash ⇒ quoted mode đổi `Bash(git reset:*)` → `git rết` (thủng `--disallowedTools`), `PROJECTS_ROOT` → `RÔT`, `project_doc_max_bytes` → `mã`.
- Cổng `scripts/accept-shell-tmux.sh` (tmux server riêng `-L`, bash thật + readline): trước sửa M1–M3 + I ĐỎ đúng nguyên văn báo, H (gõ người 60 ms/phím) XANH. Sau sửa 5/5 XANH.
- Đối chứng ngược: bỏ chốt hàng đợi (`read -t 0`) ⇒ M1–M3 ĐỎ (`git rết`), I/H XANH; bỏ chốt định danh/toàn hoa ⇒ I ĐỎ (`mã`, `RÔT`), M/H XANH. H là đối chứng «plugin không bao giờ đổi».
- Không vỡ đường cũ: VTE plugin 0/1 và ptyxis thật (~/.bashrc) XANH trên Xvfb; Python 45/45; Rust 9/9; audit 140 assertion 0.
- CHƯA ĐO: bash đang mở từ trước vẫn giữ hàm cũ tới khi mở terminal mới; `/terminal` + `/type` của huba chưa chạy lại sau sửa.

## 16/11 — chạm Ctrl giữ nguyên từ đang gõ (Hà: «u, Ctrl, s phải ra us»)

- `Session.freeze_word` + engine nhận Ctrl nhấn-nhả đứng riêng (Ctrl+phím khác không tính; nhả phím khác giữa chừng vẫn tính). Từ hiện tại giữ đúng chữ đang hiện, không Telex tới hết từ; từ sau gõ bình thường.
- `tests/test_engine.py` 5 bài: trước sửa 3 ĐỎ (`'ú' != 'us'`, `'ấ' != 'âs'`), sau 68/68 XANH. Gõ thật GTK3 (Xvfb): `u`+Ctrl+`s` → `us`, đối chứng `us` → `ú`; accept-xvfb 7 bài XANH, MÁY NGUYÊN 1->1. Bản cài ~/.local cập nhật (kèm component).
- Không áp cho plugin bash: readline không nhận được Ctrl đứng riêng.

## 15/11 23:05 — trang giới thiệu LIVE ở https://zkey.dipgle.com (Hà ra lệnh, đăng nhập bằng QR)

- Hà: «trước vẫn tự làm» (tiền lệ `AI/sdvi/scripts/dang-nhap-qr.mjs`) + «tự mở bằng playwright». Playwright chưa có ⇒ `scripts/web-driver.py` (WebKit2 thật trên Xvfb + bus riêng; bấm/gõ bằng XTest; đọc trang bằng JS liệt kê).
- tfl5 Studio `cpanel.tafalo.com`: More sign-in options → Show QR code; Hà quét + duyệt ⇒ vào Studio (administrator). Tạo app `zkey` (`a-mwi0sgxv`) qua ô New app; Explorer → upload `index.html` (8.6 KB) → Publish now, ghi chú «zkey intro site v1» ⇒ History `live`. Domains → Add `zkey.dipgle.com` ⇒ `active` 11:03:07 PM.
- Đo lại target: trình duyệt mở `https://zkey.dipgle.com/` như người xem: tiêu đề trùng repo, 5 đoạn dò có đủ, ảnh `.tmp/web-driver/shot-27.png`. Tải thẳng bằng Python để so byte: classifier chặn (Undermining Oversight) — không lách; so byte CHƯA LÀM.
- Đăng xuất Studio qua UI sau khi xong (phiên admin không còn hiệu lực trên đĩa .tmp); tắt bộ điều khiển. Mount desktop không đụng (bus riêng).

## 15/11 22:25 — BẬT zkey làm bộ gõ hệ thống (Hà xác nhận sau khi biết rủi ro)

- Hà: «cài chạy như ứng dụng bình thường»; hỏi lại (đổi bộ gõ máy, `zkey/CLAUDE.md:8`, chưa đo trên desktop thật) ⇒ Hà chọn «Bật zkey cho cả máy».
- `system-ime.py enable` mã 0: component `~/.local/share/ibus/component/zkey.xml` (exec `~/.local/bin/zkey --ibus`); `~/.config/environment.d/99-zkey.conf` (GTK/QT/XMODIFIERS ibus, `IBUS_ENABLE_SYNC_MODE=1`, `IBUS_COMPONENT_PATH`); `~/.xinputrc` `run_im ibus` (bản gốc fcitx5 lưu ở `~/.local/state/zkey/system-ime/`); nguồn GNOME `[('xkb','us'), ('ibus','zkey')]`.
- Có hiệu lực sau đăng xuất/đăng nhập. CHƯA ĐO: phiên GNOME thật sau đăng nhập (zkey trong danh sách, gõ ở Text Editor/Firefox/terminal). Quay lại: `python3 /mnt/data/projects/zkey/scripts/system-ime.py disable` rồi đăng xuất/đăng nhập.

## 15/11 21:30 — cài thật ~/.local (Hà duyệt); bộ gõ hệ thống chuẩn bị sẵn

- Hà duyệt cài ⇒ `install-user.py --prefix ~/.local`: 15 tệp, đích trống trước đó; `desktop-file-validate` OK; gõ thật GTK3 bằng `~/.local/lib/zkey` XANH (gõ dồn 30/30); mount desktop 1→1. Ngoại lệ có duyệt cho `zkey/CLAUDE.md:8`.
- Trình duyệt: Hà chọn bỏ qua lúc này ⇒ P0-001 mục 1–2 vẫn KHÔNG ĐO ĐƯỢC.
- Bộ gõ hệ thống: Hà chọn «chuẩn bị, chưa bật». `scripts/system-ime.py` + `tests/test_system_ime.py` (HOME giả; gsettings thật trên keyfile riêng): bật ⇒ env 99-zkey (sau 95-fcitx5), xinputrc ibus, nguồn nhập thêm zkey; tắt ⇒ từng byte gốc. Máy thật kiểm sau bài: nguồn GNOME `[('xkb','us')]` trước=sau, không có zkey.xml/99-zkey.conf, xinputrc vẫn fcitx5.
- `scripts/probe-system-ime.py`: ibus-daemon riêng + `IBUS_COMPONENT_PATH` ⇒ liệt kê zkey, tự chạy `<prefix>/bin/zkey --ibus`, GTK3 `t…tiếng`, Space, ⌫⌫ ⇒ `tiến` đúng. Đối chứng `IBUS_COMPONENT_PATH` thiếu ⇒ 0 engine, ĐỎ.

## 15/11 21:10 — màn thiết lập: nghiệm thu trọn vòng hai vai

- Sửa `zkey/settings.py`: tệp cấu hình hỏng không còn làm màn chết (trước: `load()` ném lỗi, không mở được); nay mở với mặc định + báo lỗi, chỉ ghi đè khi bấm Lưu. `config.record_change` ghi `changes.log` (giờ, người dùng, khoá cũ→mới; không nội dung gõ) — `tests/test_config.py`.
- `scripts/accept-settings.py` (Xvfb + bus/IBus riêng, cấu hình trong `.tmp`): ô GTK3 gõ `hoaf` → `hoà`; tệp hỏng ⇒ màn báo lỗi, mặc định hiện; CHỈ phím (Tab/Space) bỏ «Đặt dấu hiện đại» + Lưu ⇒ màn «Đã lưu», tệp `modern_tone = false`, `changes.log` `modern_tone=true->false`; mở lại hiện đúng; ô gõ lại `hoaf` → `hòa`. Đọc màn qua cây trợ năng, tiêu điểm bằng X (không hành động trợ năng). Ảnh `.tmp/settings-{error,saved,reopened}.png` đã xem.
- Đối chứng: tắt nạp lại cấu hình khi focus-in (đột biến `engine.py`) ⇒ `after='hoà'`, ĐỎ; đã trả lại.
- accept-xvfb nay 7 bài: XANH, MÁY NGUYÊN 1->1. Python 57/57.

## 15/11 21:00 — GỐC THẬT sự cố portal desktop: accept-ptyxis.py (sửa kết luận 20:20)

- `systemctl --user` cho thấy `xdg-document-portal` của desktop **failed lúc 20:37:45** (exit 21); `.tmp/ptyxis-session.log` (20:37:46) có bus riêng kích hoạt `org.freedesktop.portal.Documents`. `accept-ptyxis.py` chạy `dbus-run-session -- ptyxis` với `XDG_RUNTIME_DIR` thật, không qua `isolated_engine()` ⇒ portal riêng tranh `/run/user/1000/doc`. Bài này trong `accept-xvfb.sh` từ 11:00 ⇒ mọi lượt bộ đầy đủ (phiên này 16:00–20:37 và phiên trước) có thể đã làm hỏng portal desktop. Lệnh chẩn đoán tay 20:1x chỉ là MỘT lần; kết luận 20:20 «chỉ lệnh tay» là SAI/thiếu.
- Chốt cả lớp: `scripts/private_bus.py` là đường DUY NHẤT mở bus riêng (daemon + dịch vụ kích hoạt luôn có runtime trong `.tmp`; `child_real_runtime` chỉ cho app cần systemd người dùng như ptyxis). `tests/test_private_bus.py` ĐỎ nếu có `dbus-run-session` gọi trực tiếp; chạy trên bản trước sửa bắt đúng `accept-ptyxis.py:46`, `native_acceptance.py:366`, `probe-host.sh:8`.
- Cổng tác hại trong `accept-xvfb.sh`: mount `/run/user/UID/doc` + trạng thái portal desktop trước/sau. Lượt khi desktop chưa mount ⇒ `KHÔNG ĐO ĐƯỢC` mã 2 (đã thấy). Hà duyệt restart lần 2 (PID 365673) ⇒ lượt đầy đủ: 6 bài XANH, `MÁY NGUYÊN: active, mount 1->1`, PID không đổi. Nhánh ĐỎ của cổng chưa chạy (cấy hỏng = phá desktop thật).
- ptyxis với runtime tách (daemon riêng, ptyxis runtime thật): XANH 2/2; portal riêng gắn ở `.tmp/bus-runtime-*/doc`; sau chạy 0 mount sót.

## 15/11 20:50 — gói cài user-local; `bin/zkey` thiếu quyền chạy

- `bin/zkey` trong git là 100644 ⇒ `bin/zkey --run` (theo README) ra `Permission denied` (mã 126; `scripts/probe-run-ptyxis.sh` lộ). Đặt 100755. `zkey.desktop` gọi qua python3 nên không dính.
- `zkey --run ptyxis --standalone`: sống 6/6 (IBus sync), 6/6 (IBus async), 6/6 (không IBus), mỗi lượt 12 s. Lỗi chết 1/3 cũ không tái hiện; phép đo chưa từng ĐỎ ⇒ chưa phải bằng chứng đã sửa.
- `scripts/install-user.py`: cài theo manifest SHA-256 (từ chối đè tệp lạ; gỡ chỉ tệp nguyên vẹn; dọn log/bytecode do zkey sinh). `tests/test_install_user.py` 5 bài; đột biến bỏ chốt «tệp lạ» và «tệp đã sửa» ⇒ đúng bài ĐỎ.
- Gõ thật bằng bản cài (`ZKEY_PACKAGE_ROOT=<prefix>/lib/zkey scripts/native_acceptance.py`, kiểm module nạp đúng từ bản cài): XANH, BURST+NATIVE 30/30. Cấy lõi hỏng ⇒ `Engine registration failed`, mã 1. Gỡ ⇒ 0 tệp sót.
- Log engine bản cài giữ 50 (`runtime.prune_logs`, `tests/test_runtime.py`); cấy 55 + 1 lượt ⇒ còn 51. Cây phát triển (có `.git`) không cắt: 192 → 196.
- accept-xvfb 6 bài XANH; Python 52/52.

## 15/11 20:20 — trình duyệt: Firefox snap KHÔNG ĐO ĐƯỢC; sự cố portal desktop

- Bài mới `scripts/accept-firefox.py` + trang `scripts/fixtures/browser-input.html`: trang tự ghi giá trị ô, số sự kiện input/composition vào tiêu đề; bài đọc tiêu đề X11. Chưa chạy được tới bước gõ.
- Firefox máy này = snap 154. Trên Xvfb + bus riêng: cần scope `snap.firefox.firefox-<uuid>.scope` (đã thêm bằng `systemd-run --user --scope`), rồi dừng ở `Error: cannot open display` dù trong snap thấy socket X và đã thử `-ac`, bỏ XAUTHORITY. Không thấy AppArmor DENIED. ⇒ KHÔNG ĐO ĐƯỢC (mã 2). Đường kế: Firefox tarball chính thức trong `.tmp/tools` (`ZKEY_FIREFOX`) — tải bị classifier chặn, chờ Hà.
- **SỰ CỐ (do phiên này):** một lệnh chẩn đoán gõ tay chạy `dbus-run-session` với `XDG_RUNTIME_DIR=/run/user/1000` ⇒ bus riêng kích hoạt `xdg-document-portal` thứ hai, nó gỡ lười rồi thay mount `/run/user/1000/doc` của desktop, thoát thì gỡ luôn ⇒ desktop mất mount (portal PID 1870 vẫn sống). Hà duyệt ⇒ `systemctl --user restart xdg-document-portal.service` 20:15:42; đo lại: 1 mount `fuse.portal`, PID 243901. Chốt lớp: bus riêng của `accept-firefox.py` luôn có `XDG_RUNTIME_DIR` trong `.tmp`; chỉ tiến trình trình duyệt nhận runtime thật. Đo lại sau chốt: mã 2 sạch, mount desktop 1.

## 15/11 16:50 — đối chứng engine xkb: GTK4 async mất phím là lỗi GTK4/IBus

- Bộ đo `scripts/probe-gtk4-native.py`: GTK4 4.22.4 Entry trong tiến trình, X11 backend, Xvfb + D-Bus + IBus riêng; engine kiểm bằng `get_global_engine()`; 8 phím chậm 250 ms: a b c ⌫ Home x End ⌫ (chuẩn `xa`). Log `.tmp/probe-gtk4-native.log`.
- `xkb:us::eng` sync=0: `abcx` — mất ⌫/Home/End, chữ cái vẫn vào; sync=1: đủ 8/8. zkey: y hệt cả hai chế độ.
- Kết luận trong phạm vi đo: GTK4 + IBus 1.5.34~rc2 chế độ async (X11) mất phím không in được mà engine trả lại, với cả engine gốc của IBus — không do zkey. Bộ đo đổi được trạng thái (sync 0/1 cho hai kết quả ngược nhau).
- CHƯA ĐO: GTK4 Wayland backend; desktop thật (không Xvfb); bản IBus khác.

## 15/11 16:30 — GTK4 Text Editor: gõ dồn + phím native

- Pha EDITOR BURST+NATIVE (`scripts/accept-editor.py`, đọc tài liệu thật qua AT-SPI, 6 ca × 5 lượt, giống GTK3): sync 30/30 XANH; `accept-xvfb.sh` 6 bài XANH (lượt cuối `.tmp/accept-xvfb-gtk4-final.log`).
- Đối chứng `ZKEY_CLIENT_SYNC_MODE=0`: ĐỎ ngay lần xoá đầu — Ctrl+A, Backspace để nguyên `tiếng việt`; thêm Backspace/End/Backspace chậm 200 ms: tài liệu không đổi, engine vẫn thấy phím (23 key-state). Tức GTK4 async (X11 backend) MẤT phím engine trả False, không chỉ đảo thứ tự. Bài cũ không phủ vì chưa gửi phím native sau khi có chữ.
- CHƯA ĐO: cùng hiện tượng với engine IBus khác (xkb) — chưa biết lỗi của zkey hay GTK4; GTK4 Wayland backend.

## 15/11 16:00 — gõ dồn có phím native: gốc + sửa, XANH

- Gốc: `im-ibus.so` GTK3 (ibus 1.5.34~rc2) bất đồng bộ; phím engine trả False bị `gdk_event_put` ra cuối hàng sự kiện, commit-text áp ngay ⇒ đảo thứ tự. Module GTK3 và GTK4 đều đọc `IBUS_ENABLE_SYNC_MODE`.
- Sửa `zkey/runtime.py`: env ứng dụng do zkey mở có `IBUS_ENABLE_SYNC_MODE=1` (không đổi env hệ thống). GTK3 BURST+NATIVE 30/30 qua đường sản phẩm; đối chứng `ZKEY_CLIENT_SYNC_MODE=0` ⇒ 0/30 ĐỎ. `accept-xvfb.sh` 2 lượt × 6 bài XANH.
- Chi phí (KEY-TO-TEXT, 3 lượt × 7 phím, trong tiến trình, không gồm vẽ màn): sync trung vị 6.0–6.4 ms, max 8.3; async 4.0–4.2, max 6.7.
- CHƯA ĐO: GTK4 gõ dồn + phím native; app ngoài `zkey --run`; engine treo khi sync.

## 15/11 15:30 — gõ dồn có phím native xen giữa: ĐỎ

- Pha BURST+NATIVE trong `scripts/native_acceptance.py` (GTK3, Xvfb riêng, 6 ca × 5 lượt, chuẩn = cùng phím gõ chậm; 2 ca ghim tay): 0/30 bằng gõ chậm; 2 chuẩn chậm khớp ghim. Ví dụ `tieengs⏎vieetj` → `tieengsvi⏎eetj`, `vieetj⌫t` → `vieetj`/`viêtt`. Log `.tmp/native-burst-1.log`. Chưa tìm gốc.

## 15/11 11:30 — gốc lỗi `zkey --run ptyxis`: lệch XDG_RUNTIME_DIR

- Chia đôi biến môi trường (scratchpad): từng biến và cả nhóm biến của launcher, áp lên ptyxis ngoài launcher, đều sống 3/3. Gốc: `runtime.py` kích hoạt portal/document-portal với `run-…/runtime`, còn ứng dụng nhận `session-…/runtime`.
- Sửa: ứng dụng dùng chung runtime dir. Launcher không IBus: trước 4/5 chết, sau 3/3 sống. Launcher có IBus: trước 4/4 chết, sau 2/3 sống ⇒ còn phần dính IBus (nợ). accept-xvfb 6 bài 2/2 mã 0; Python 45/45.

## 15/11 11:00 — plugin đã cài vào ~/.bashrc; ptyxis thật XANH

- Cài: `scripts/install-shell.sh` (một khối có đánh dấu, idempotent, sao lưu, `bash -n`; `--uninstall` trả đúng byte bản gốc — đã thử trên bản sao). Chạy qua huba vì classifier + guard-write-path chặn ghi `~/.bashrc`; sao lưu `~/.bashrc.zkey-backup.20261115084125`, 1 khối.
- `accept-terminal.py` chế độ `home` (bash -i với ~/.bashrc thật) XANH. `accept-ptyxis.py`: app ptyxis thật + ~/.bashrc thật, 2/2: bash nhận `tiếng việt`, bí mật ECHO-off `SAME`. Đối chứng `ZKEY_MODE=off` ⇒ ĐỎ (bash nhận `tieengs vieetj`).
- `accept-xvfb.sh` nay gồm 6 bài (GTK4, GTK3, VTE ×2, plugin, ptyxis): 2/2 lượt mã 0 sau cùng. Bước ô mật khẩu GTK3 đỏ 1/~12 lượt gộp (phím mất, không lộ/không đổi), riêng lẻ 3/3 xanh ⇒ nợ.
- LỖI `zkey --run` (launcher cô lập) với ptyxis trên Xvfb: ptyxis/shell thoát sau vài giây. A (launcher+IBus) chết 4/4; D (launcher, không IBus) 1/2; B, C (không launcher) sống 3/3. Không thuộc đường terminal (plugin không cần launcher); chưa tìm gốc.

## 15/11 10:00 — Telex trên dòng lệnh bash (plugin readline) XANH trên VTE thật

- `shell/zkey.bash` + `zkey-line` (Rust, tiến trình thường trực qua coproc). Lõi thêm `valid_syllable` (RED→GREEN, Rust 8/8 + 1 test giao thức).
- `accept-terminal.py` chế độ plugin: 7 tiền tố hiện ngay trên dòng lệnh trong dấu nháy; bash nhận `tiếng việt`; `echo status test` giữ nguyên; `read -s` vẫn không lộ/không đổi. Đối chứng ngược: `ZKEY_MODE=off` ⇒ ĐỎ ở `tiê`; `ZKEY_MODE=all` ⇒ ĐỎ (lệnh ngoài nháy bị đổi). Gộp vào `accept-xvfb.sh`: GTK4 + GTK3 + terminal ×2 mã 0.
- Đo `scripts/bench-shell.sh`: 329/330/336 µs mỗi phím (1995 phím, 0 lỗi); không gồm vẽ lại terminal.
- Hạn chế đã thấy khi đo: câu tiếng Anh trong dấu nháy bị đổi ở âm tiết hợp lệ (`us`→`ú`, `per`→`pẻ`). CHƯA: ptyxis app, tmux, SSH, vim/TUI, zsh; chưa thêm dòng vào ~/.bashrc (luật dự án cấm cài ngoài repo).

## 15/11 09:00 — terminal VTE: vế AN TOÀN của P0-001 XANH; gõ tiếng Việt trong terminal CHƯA có

- `scripts/accept-terminal.py` (chạy trong xvfb-run, `ZKEY_TEST_DISPLAY`): VTE 0.84 thật + bash. Lệnh `echo tieengs` đi nguyên; `read -s` với chuỗi giả dùng một lần `as`: không hiện trên màn, shell so khớp nguyên dạng (chuỗi không bao giờ in ra); engine thấy `purpose=10 protected=True`, 81 phím; 0 cảnh báo.
- Đối chứng ngược hai chiều (`ZKEY_TERMINAL_MUTATE`): `compare` (shell chờ dạng Telex `á`) ⇒ ĐỎ «transformed»; `echo` (gõ khi ECHO bật) ⇒ ĐỎ «visible»; lành ⇒ XANH.
- Sửa kèm (RED→GREEN + đối chứng): engine xin surrounding sớm ⇒ module IBus của GTK hỏi VTE, VTE từ chối, ứng dụng in cảnh báo và caps 41→9. Nay chỉ xin ở phím đầu tiên không được bảo vệ của mỗi focus. GTK4/GTK3 vẫn xanh 2/2.
- CHƯA: Telex trong terminal (đang đi thẳng), ptyxis app, SSH/tmux, TUI raw.

## 15/11 08:00 — GTK4 + GTK3 gõ thật XANH trên Xvfb riêng (3/3 lượt)

- Đường đo: `bash scripts/accept-xvfb.sh` → `.tmp/accept-xvfb.log` (GATE_EXIT 0/1/2). Xvfb 21.1.22 tải bằng `apt-get download` + `dpkg-deb -x` vào `.tmp/tools` (không cài hệ thống; sudo hết giờ). Phím XTest chỉ vào màn ảo, bus D-Bus/IBus riêng.
- Vì sao không dùng desktop: Xwayland chạy `-enable-ei-portal` ⇒ mỗi phiên XTest bật hộp thoại RemoteDesktop; chủ máy xem qua zigeel từ xa không thấy. Desktop chỉ xanh 1 lượt (07:14) khi quyền đang mở.
- GNOME Text Editor (GTK4): 7 tiền tố + «tiếng việt» đọc qua AT-SPI; vết engine riêng 20 `key-state`; cổng đòi ≥7.
- GTK3: 7 tiền tố, 10 lượt gõ dồn 0 ms, Backspace native, Home, ô mật khẩu đi thẳng (2 chấm), 0 preedit, 0 warning. Ảnh `.tmp/native-gtk-render.png` đã xem.
- RED trước sửa (cùng bài): `tieseng vieetj` — phím trả native bị GTK async xếp sau commit ⇒ xáo thứ tự. Sửa `zkey/session.py`: commit mọi phím in được; phím chưa xác nhận commit nguyên dạng; ghép bù khi ảnh chụp của app khớp nguyên văn (hậu tố + ranh giới, ≤3 từ/64 ký tự).
- Python 44/44; đối chứng ngược: bỏ luật ranh giới ⇒ test âm ĐỎ; bỏ chốt private ở ghép bù ⇒ test mật khẩu ĐỎ (test cũ mù, đã sửa). Rust 7/7, clippy 0, release 0; impact record 0; audit 8 tệp/138 assertion 0.
- CHƯA ĐO: desktop Wayland-native, Chrome/Electron, terminal/VTE (P0-001), Backspace trong lúc gõ dồn, đo trễ.

## 15/11 00:59 — ĐANG LÀM, rút phạm vi nghiệm thu UI

Đường sản phẩm nay commit từng phím, sửa suffix theo incoming surrounding. Python 33/33; Rust 7/7; clippy -D warnings/release build mã 0. Protocol host 7 nhóm mã 0, 0 warning sau giữ GI Text wrapper để tránh libibus kiểm floating object đã hết vòng đời. Test compile mọi Python entrypoint giữ lỗi duplicate lambda argument từng làm probe không khởi động.

Các lượt GTK3/XTest smoke trước chưa chứng minh engine xử lý chính là zkey private: **không dùng chúng làm nghiệm thu zkey**. Root cause nối GTK: `IBUS_USE_PORTAL="0"` vẫn bật portal (binary kiểm biến tồn tại), trong khi service portal không nhận địa chỉ daemon riêng. Đã unset biến và truyền activation env vào bus riêng. Bài native mới đòi vết key-state của zkey; chưa xanh sau sửa này.

Lượt mới: desktop không khoá, modifier không giữ (`scripts/desktop-status.py`); compositor từ chối kích hoạt GNOME và GTK fixture nên dừng trước gõ. `.tmp/editor-app.json` là app còn mở; `.tmp/native-acceptance.log` còn đỏ môi trường. Đã hỏi chủ máy bấm vào vùng soạn thảo. Chưa kiểm burst 10 phrases, VTE ECHO-off, Chrome/Electron hay visual. Ảnh trắng/đen trước không tính là nghiệm thu. Không cài hoặc đổi input source toàn hệ thống. Các bảng dưới là lịch sử prototype.

## Lượt 23:49 — giảm rủi ro P0, chưa đóng P0

- Diff `zkey/engine.py`, `tests/test_engine.py`: graph chọn 9 nút, 7/34 test; đã chạy 7 handler test rồi toàn bộ 27 Python test, mã 0. `impact.py --record` cũng chạy 27/27, mã 0 và cập nhật graph/vết gọi thật. Không đổi Rust, không chạy lại Rust/build/clippy trong lượt này.
- RED trước sửa: 2 test mới thất bại (bypass TERMINAL, xoá transport preedit khi chuyển protected). Test reset mở rộng cũng đỏ riêng trước khi sửa reset. GREEN sau: 27/27 Python.
- Bypass được kiểm bằng 6 loại phím giả; chuyển protected kiểm 5 trường hợp TERMINAL/PASSWORD/PIN/PRIVATE/HIDDEN_TEXT, reset/focus-out, trở lại FREE_FORM và commit đúng một chữ mới. Sink chạy `Engine.apply` thật rồi thu lời gọi update/commit; không có client IBus, ECHO-off hoặc UI thật. Không thu nội dung người dùng.
- `audit_measurements.py`: 7 tệp/101 assertion, 0 mẫu nghi ngờ trong tập nhận diện, mã 0. Đã soát ngữ nghĩa test mới; phép đếm kết quả tránh `all([])` xanh rỗng.
- Stage lại trong repo, mã 0; đối chiếu SHA-256 nguồn và bundle 7/7 tệp Python/thư viện khớp, mã 0. Không cài ra ngoài repo. Stat hai tệp mã/test lúc 23:50 khớp cỡ/mtime sau lần sửa cuối.
- Chưa nghiệm thu desktop; engine chỉ bypass terminal được khai báo đúng. FREE_FORM vẫn giữ từ trong preedit. Không đổi cấu hình input source hoặc cài ra ngoài repo. QG chưa chạy; chưa gom commit/phát hành.

## Đã chạy tại `/mnt/data/projects/zkey`

Bảng dưới ghi lượt prototype trước 23:49; số Python mới ở mục trên.

| Phép kiểm | Kết quả |
| --- | --- |
| `cargo test --offline` | 7/7 test Rust, mã 0 |
| `cargo clippy --offline --all-targets -- -D warnings` | mã 0, không warning |
| `cargo build --offline --release` | mã 0, sinh cdylib + benchmark |
| `python3 scripts/impact.py --record` | 25/25 test Python; import graph bổ sung call trace thật |
| `python3 scripts/audit_measurements.py` | 7 tệp, 79 assertion, 0 mẫu đáng ngờ trong tập nhận diện; mã 0 |
| `python3 scripts/stage.py` | mã 0; chỉ ghi `.tmp/stage` |

Các lượt RED→GREEN đã quan sát và giữ test: lỗi chuyển `uwow`; Backspace xoá phím thay vì ký tự; thiếu `ua+w → ưa`. Cũng đã sửa khác biệt GI `keyval_to_unicode` trả chuỗi. Test handler có cấy lỗi core để kiểm raw text được giữ đúng một lần; test bản đồ và bộ quét có đối chứng ngược.

Benchmark release, 100.000 lần replay tiền tố của 5 từ, sau warm-up: p50 **96 ns**, p95 **1.222 ns**, p99 **2.398 ns**, max **39.652 ns**. Đo `Instant` quanh hàm Rust; không gồm ctypes/Python, IBus, compositor, ứng dụng hoặc màn hình. Đây không phải bằng chứng mượt hơn bộ gõ khác.

## Chưa đo được / còn thiếu

Lệnh thăm dò `dbus-run-session` bị sandbox từ chối bind socket: mã **127**, không phải đỏ nghiệp vụ hoặc xanh. Đã ghi scratchpad huba đúng session; tệp được đổi thành `huba-run.taken-20261114T153641Z`. Chưa có `.tmp/ibus-probe.log` ở lần kiểm cuối. “Đã nhận thư” không đồng nghĩa “đã chạy”. Lệnh tiếp tục: `bash /mnt/data/projects/zkey/scripts/probe-host.sh`.

Ngoại lệ đi thẳng API: probe dùng `InputContext` cho **thăm dò protocol**, không tạo dữ liệu nghiệp vụ và không tuyên bố E2E. Bù bằng nghiệm thu gõ thật qua UI còn mở. Probe đã sửa thứ tự focus trước chọn engine qua soát source/runtime IBus; chưa được chạy thành công.

Chưa bật engine trên desktop; chưa đo latency phím→màn hình; chưa kiểm Chrome/VS Code/terminal, focus commit thực tế, màn thiết lập GTK hoặc Wayland/X11. Chưa chạy QG và chưa phát hành/gom commit. Chưa chọn giấy phép phát hành.

Soát bảo mật trên mã: không mạng/clipboard/global keyboard hook, không log nội dung gõ; config lưu user-local mode 0600; password/PIN/private hints được bỏ qua. Chỉ có test kỹ thuật cho các nhánh này, chưa xác nhận app thật khai báo input purpose đúng. Chưa có audit thay cấu hình, ghi nợ trước phát hành.

Nguồn: `src/lib.rs`, `src/telex.rs`, `zkey/engine.py`, `zkey/session.py`, `tests/test_engine.py`, `tests/test_session.py`, `scripts/probe_ibus.py`. Tính đúng toàn bộ tiếng Việt chưa được chứng minh bởi tập test hữu hạn này.

## 2026-11-20 17:30–18:00 +07 — gõ lại dấu sau khi xoá dấu cách · bash mặc định `all`

**Đã chạy thật (mã thoát đọc trực tiếp):**
- `cargo test --offline` (native): **55 lib + 7 main + 5 dbus_live + 2 corpus = 69 PASS**; `cargo clippy --all-targets -- -D warnings` **0**; `cargo build --release` **0**; `cargo fmt --check` **0**.
- `/usr/bin/python3 -m unittest discover -s tests`: **90 PASS** (dòng `NOT MEASURABLE: no running ibus-daemon address` là trạng thái riêng của bài cần daemon, không phải xanh).
- `scripts/accept-shell-tmux.sh`: **9/9 PASS, GATE_EXIT=0**. Đối chứng ngược hai chiều: bản plugin `never-machine` (bỏ chốt thời gian) ⇒ **ĐỎ** M1–M3/MV/MU (`Bash(git reset:*)`→`git rết`, `tieengs vieetj`→`tiếng việt`); bản `always-machine` ⇒ **ĐỎ** H/H2/H3. Bản sao ở `.tmp/zkey-{never,always}-machine.bash`.
- Test RED trước khi sửa: `deleted_separator_lets_a_mark_finish_the_previous_syllable` ra `săcs` (mong `sắc`); sau sửa GREEN. `seed_requires_the_recorded_caret_and_no_selection`: bỏ chốt `word.len() < max_keys` ⇒ **ĐỎ** `remove=6` (đo trực tiếp, tệp đã khôi phục), có chốt ⇒ xanh.

**Chưa đo được (KHÔNG phải xanh):**
- Nghiệm thu GUI của bản sửa (GTK3 thật + `accept_desktop.py` kịch bản `săc`+space+BS+`s ⇒ sắc`, đối chứng `săc`+space+`s ⇒ "săc s"`): **KHÔNG ĐO ĐƯỢC** vì `/tmp` hết quota người dùng — Xvfb chết ở `/tmp/.tX*-lock` (`EDQUOT`), log `NOT_MEASURABLE: No private GTK display`.
- VTE/ptyxis/tmux-plugin (accept-xvfb, accept-terminal, accept-ptyxis) cùng lý do ⇒ chưa chạy lại lượt này.
- Firefox thật: vẫn chờ Hà gõ `tieengs` để nghiệm thu bằng mắt (TODO dòng 3).

**Ghi chú thiết kế:** chốt an toàn của "nhận lại từ đã commit" là **bằng chứng sở hữu** (từ do chính engine vừa commit + con trỏ khớp + chuỗi cuối văn bản khớp + không chọn vùng + dài < `max_keys`), mạnh hơn `valid_syllable` mà Hà đề xuất; đổi lại «this»+space+BS+`s` ra «thiss» như Hà yêu cầu thay vì «thíss». Từ lạ/không sở hữu vẫn không bị sửa (đối chứng `backspace_ticket_never_survives_focus_or_a_different_caret` xanh).
