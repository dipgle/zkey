# zkey native — bản viết mới

Hà giao ngày 16/11/2026: tự thiết kế, viết lại, kiểm thử; không dùng gói bộ gõ khác hoặc crate bên ngoài. Đây là cây phát triển độc lập, **chưa thay sản phẩm đang cài**.

## Ranh giới phụ thuộc

- Rust và thư viện chuẩn; Cargo không có dependencies.
- Giao tiếp desktop dùng ABI công khai của **GLib/GObject/GIO, IBus và GTK3 hệ thống**. Launcher gọi `dbus-daemon`/`ibus-daemon` của Ubuntu. Đây vẫn là phụ thuộc hệ thống, không phải «không cần hệ điều hành».
- Không nhập module Python, không liên kết `zkey-core`, không chép implementation cũ. Bảng chữ tiếng Việt và giao thức IBus là dữ liệu/quy ước tương thích, không phải gói mã bộ gõ.
- Bản cũ, bài kiểm và bằng chứng được giữ nguyên để đối chiếu, không xoá hoặc tự cài đè.

## Cấu trúc bản mới

| Tệp | Trách nhiệm |
|---|---|
| `src/compose.rs` | Lõi Telex tăng dần, chữ NFC/chữ hoa, dấu muộn, hoàn nguyên; không I/O |
| `src/session.rs` | Quyền sở hữu từ, snapshot/caret/selection, bỏ qua protected context; ticket có xác nhận cho Reset sau Backspace thật |
| `src/desktop.rs`, `engine.xml` | Xuất Factory/Engine D-Bus bằng GIO; không dựa offset vtable của lớp GObject |
| `src/ffi.rs` | Binding ABI hệ thống tối thiểu, quản lý tham chiếu GVariant/GObject; không deserialize GObject tuỳ ý từ client |
| `src/config.rs` | Schema TOML chặt, khoá ghi của OS, audit intent → atomic rename → audit commit; phát hiện lần lưu bị gián đoạn |
| `src/settings.rs` | Cửa sổ native: bật/tắt, kiểu dấu, giới hạn từ, cho phép thử nghiệm; báo lỗi và lưu qua UI |
| `src/launch.rs` | Bus + IBus riêng, giám sát tiến trình, giữ dữ liệu phục hồi của ứng dụng ngoài cây runtime tạm; không đổi bộ gõ máy |
| `build.rs` | Nhúng SHA-256 của chính nguồn được biên dịch; dùng `sha256sum` hệ thống lúc build, không phải phụ thuộc runtime |
| `tools/stage.py` | Công cụ đóng gói phát triển, không cài; đối chiếu hash nguồn/binary, kèm source và manifest |

Python/GI/XTest trong `tests/` chỉ là **bộ kiểm**, không phải mã sản phẩm hay phụ thuộc chạy của gói native. Các helper cô lập bus/đọc cây trợ năng của workspace được dùng cho kiểm, không được nhập hoặc đóng gói vào runtime.

## Cách chạy bản phát triển

```sh
native/target/release/zkey-native --settings
native/target/release/zkey-native --run [ứng-dụng tham-số]
native/target/release/zkey-native --experimental-rewrite --run [ứng-dụng tham-số]
native/target/release/zkey-native --compose tieengs
native/target/release/zkey-native --line
native/target/release/zkey-native --build-info
```

- Không tham số: mở thiết lập native, không cần cửa sổ terminal giữ chương trình. Các tệp menu `.desktop` được stage với `Terminal=false`, **chưa cài menu hệ thống**.
- `--run` tạo phiên riêng; mặc định mở Text Editor `--standalone`. Không tự đổi nguồn nhập GNOME hoặc đụng IBus/fcitx5 desktop.
- **Mặc định rewrite TẮT: phím nguyên trạng, không phải Telex đã hỗ trợ.** Chỉ cờ thử nghiệm hoặc lựa chọn rõ ràng trên màn thiết lập mới bật đường delete+commit chưa được chứng nhận. Màn có cảnh báo WebKit.
- Cấu hình riêng: `$XDG_CONFIG_HOME/zkey-native/config.toml`; bản cũ dùng đường khác. `ZKEY_NATIVE_CONFIG_PATH` chọn tệp khi kiểm. Lưu có `generation` và `changes.log`; audit chưa commit thì cấu hình không được coi là hợp lệ.
- `ZKEY_NATIVE_TRACE=1` chỉ ghi metadata trong phiên riêng, không ghi keyval/nội dung chữ. Không dùng trace làm bằng chứng ảnh đã hiện.
- Dữ liệu/cấu hình ứng dụng được giữ ở XDG gốc của ứng dụng; chỉ dịch vụ bus dùng cây riêng. Runtime tạm chỉ xoá sau khi bus đã dừng và không còn mount riêng. Lỗi thì giữ cây chẩn đoán và trả mã thất bại.
- `--engine` từ chối bus/runtime desktop thật. **Chưa có cài/bật toàn hệ thống, plugin bash native, VNI, vim/zsh/SSH hoặc chứng nhận Wayland/Chrome/Electron.** Không tự dùng plugin cũ làm bằng chứng cho bản viết mới.

## Nghiệm thu và điểm chặn

1. Lõi Telex/state machine mới, giới hạn bộ nhớ và test Unicode/hoàn nguyên.
2. Engine native trên IBus/bus riêng; gõ bằng phím thật vào ứng dụng thật.
3. Thiết lập/launcher native, đóng gói thử trong repo; lỗi/bypass phải nhìn thấy.
4. Ma trận GTK/browser/terminal/Wayland, tốc độ và hồi quy; chỉ phát hành phần đã nghiệm thu.

**Chặn còn giữ:** WebKit không chuyển lệnh xoá tới editor; IBus delete+commit không có atomic ACK. Không nhận việc gọi API thành công là bằng chứng chữ đã sửa; không dùng Backspace giả, clipboard hoặc bắt bàn phím toàn hệ thống. Viết mới chưa tự đóng được chặn này.

Kết quả mới nhất và điều chưa đạt ở [`../docs/native-rewrite.md`](../docs/native-rewrite.md). Gói stage có nhãn **development-not-release**, không phải bàn giao sản phẩm cuối.

Chạy kiểm từ gốc zkey:

```sh
cargo test --offline --manifest-path native/Cargo.toml
cargo clippy --offline --manifest-path native/Cargo.toml --all-targets -- -D warnings
cargo build --offline --release --manifest-path native/Cargo.toml
/usr/bin/python3 -m unittest discover -s native/tests -v
/usr/bin/python3 scripts/impact.py --record
```

Các bài phím thật phải chạy trên **Xvfb riêng**, đặt `ZKEY_TEST_DISPLAY=$DISPLAY`; không trỏ sang desktop. Entrypoint: `tests/accept_desktop.py` (GTK3, `ZKEY_NATIVE_GTK4=1`, `ZKEY_NATIVE_WEBKIT=1`, `ZKEY_NATIVE_SETTINGS=1`) và `tests/accept_launcher.py` (launcher Rust thật; `ZKEY_NATIVE_VTE=1` thêm ECHO-off VTE). `ZKEY_NATIVE_SAFE_MODE=1` kiểm bypass; thêm `ZKEY_NATIVE_EXPECT_TELEX=1` là đối chứng **phải ĐỎ**, không phải cách chạy sản phẩm.

`ZKEY_NATIVE_HEALTH_FAULT=1` ở launcher kiểm lỗi cấu hình khi đang chạy: cấy tệp hỏng như fault fixture, nhìn hộp thoại thật, xác nhận phím nguyên trạng, sửa qua màn thiết lập rồi gõ Telex lại. Chạy riêng lượt này với lượt VTE. Mọi lượt UI kiểm SHA-256 của **nguồn hiện tại** trước/sau nghiệm thu; trace engine phải cùng hash. Artifact nguồn cũ bị từ chối, không chỉ tự so hai lời khai của cùng binary.

Đóng gói thử: `python3 native/tools/stage.py .tmp/<thư-mục-mới> --deb`. Từ chối đè cây cũ hoặc binary không trùng nguồn; không gọi apt/dpkg install, không có postinst/đổi IME. Bản `.deb` hiện nhắm **Ubuntu amd64**, đo yêu cầu GLIBC từ ELF; chưa công bố tương thích mọi bản Ubuntu. Source biên dịch/đóng gói được kèm trong gói. Chỉ cài khi có nghiệm thu và cho phép riêng.
