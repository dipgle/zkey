# zkey/core — native (19/11 trưa, phiên kế nhiệm DeepSeek)

XONG trong mã (chưa commit lúc ghi): (1) **Firefox** — gốc = client gọi `Reset` sau MỖI phím (14/14 `edit sent remove=0 insert_chars=1`); `client_reset` cũ xoá từ ⇒ không sửa dấu. Sửa `native/src/session.rs`: Reset treo trạng thái, snapshot kế xác nhận `owns` rồi mới ghép; test `client_reset_after_every_commit_keeps_the_word_composable` RED `tieengs`→GREEN `tiếng`. **Chưa cài lại binary** (cần Hà duyệt) nên CHƯA đo Firefox thật. (2) **Plugin bash** dùng `zkey-native --line [traditional]`; thêm `valid_syllable` (giữ `status`, không thành `státu`) + test; `accept-shell-tmux.sh` 5/5 GATE 0 (đã ghim `ZKEY_MODE=quoted`, trước đó kế thừa `off`). `stage.py` chép `zkey-native` khi có build.
ĐO: native test 50+7+5+2, clippy 0, release 0; lõi cũ test/clippy/build 0; Python 90; ma trận 8 lane GATE 0, harm portal active→active/mount 1→1.
CHƯA: Firefox thật (cần cài lại); WebKit N01 vẫn ĐỎ; VTE/ptyxis thật với plugin mới.
CHỜ HÀ: (a) duyệt `native-ime.py disable` + `enable --trace` để đo bản sửa Firefox; (b) quyết bỏ cấm Backspace qua IBus (dòng cấm do phiên đầu tự ghi).
DỞ GIỮA: một phiên khác đã commit `1ff942a` (TODO Firefox lần 2) lúc 11:07 khi phiên này đang sửa cùng cây; hiện không còn tiến trình zkey nào khác (đo `ps`). Nền: KHÔNG.
