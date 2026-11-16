# Dùng lại hạ tầng hay viết lại — số đo 16/11/2026

## Những gì kiểm chứng được

- Lõi Telex triển khai tại `src/telex.rs`, xuất FFI tại `src/lib.rs:13`; `zkey/core.py:8–17` gọi chính `libzkey_core.so`. `Cargo.toml` không khai dependencies; `Cargo.lock:5–7` và `cargo tree --offline` chỉ có gói zkey-core. Đây là bằng chứng **không liên kết crate bộ gõ khác**, không phải kiểm toán xuất xứ/clean-room từng dòng mã.
- Adapter của dự án dùng Python/GObject/IBus (`zkey/engine.py:6–12`), launcher tạo IBus riêng (`zkey/runtime.py:70–80`). Hạ tầng và ứng dụng Ubuntu vẫn dùng thư viện hệ thống: không được đồng nhất «lõi tự viết» với «không còn phụ thuộc».
- Trong tập `src/`, `zkey/`, `shell/`, Cargo.toml/lock được kiểm bằng git grep, không thấy lời gọi/nhắc Unikey/Bamboo/OpenKey/EVKey. Phạm vi này không chứng minh toàn bộ hệ điều hành không dùng chúng.

## Lỗi WebKit: đã có đối chứng nguyên nhân, chưa có bản sửa sản phẩm

Binary WebKitGTK2.52.6 đang cài: constructor `WebKitInputMethodContextImplGtk` tại0xf27870–0xf27982 nối preedit-start/changed/end, commit, retrieve-surrounding, **không nối delete-surrounding**. Signal công khai tương ứng của WebKit vẫn tồn tại.

`scripts/accept-webkit.py` trên Xvfb/bus riêng:

1. Stock: `tiee` → `tieê`, engine gửi delete(-1,1), WebKit context chỉ thấy commit. Bài ĐỎ mã1.
2. `ZKEY_WEBKIT_DIAGNOSTIC_BRIDGE=1`: chỉ nối callback Gtk.IMMulticontext→WebKit.InputMethodContext còn thiếu **trong ứng dụng kiểm**, không đổi core, adapter IBus hoặc thư viện hệ thống. Bài XANH:7 tiền tố, tiếng việt, Backspace, password giả nguyên,0 composition;23 input events/20 engine keys. Trace `.tmp/run-7p_xe3te.log`.

Đối chứng này chứng minh đầu nối thiếu có thể gây lỗi nhân chữ. KHÔNG chứng minh mọi lỗi gõ đều do upstream; KHÔNG gọi nhánh diagnostic là bản sản phẩm đã sửa. Chưa cài workaround cho ứng dụng người dùng. Không dùng LD_PRELOAD/interpose toàn bộ ứng dụng chỉ để làm bài kiểm xanh; một đường sửa sản phẩm phải có phạm vi/ABI/lifetime được kiểm và nghiệm thu ứng dụng thật.

## Chi phí Python→Rust đo riêng

Hai chương trình dùng cùng5 từ và lịch tiền tố;100.000 mẫu, warm-up5.000 lần:

| Phép đo | p50 | p95 | p99 | max quan sát |
| --- | ---: | ---: | ---: | ---: |
| `target/release/zkey-bench` — Rust replay |99ns|1.099ns|2.152ns|5.379.578ns|
| `python3 scripts/bench-ffi.py` — UTF-8+ctypes+Rust |2.222ns|5.469ns|6.601ns|8.046.983ns|

Đây là hai lượt microbenchmark riêng, không phải phép trừ nhân quả chính xác. Không loại thời gian bị hệ điều hành ngắt lịch; không tự kết luận nguyên nhân các mẫu max. Không có IBus, widget, compositor hoặc thời điểm pixel hiện. Vì thế **không dùng bảng này tuyên bố độ mượt/tối ưu toàn hệ thống**. Phép đo widget cũ cũng chỉ có7 phím/lượt và không gồm vẽ màn (`scripts/native_acceptance.py:194–207`).

## Các phương án

| Phương án | Có thể cải thiện | Không tự giải quyết |
| --- | --- | --- |
| Giữ core, sửa đúng hợp đồng/adapter tương thích | Tránh mất/nhân chữ do giao tiếp; thay đổi nhỏ, có ca tái hiện | Frontend không cung cấp thao tác sửa đáng tin vẫn cần hợp tác/fallback |
| Viết mới adapter native Rust, giữ core | Bớt Python/FFI, chủ động hàng sự kiện/giám sát; phải đo A/B | Callback editor bị thiếu, bảo mật terminal, chính sách Wayland |
| Viết lại toàn bộ zkey, gồm core Telex | Tự thiết kế lại hoàn toàn phần do dự án sở hữu | Không loại bỏ IBus/compositor/app contracts; phải kiểm lại mọi quy tắc Telex và toàn bộ ma trận ứng dụng |
| Thay cả input stack/toolkit hệ thống | Can thiệp sâu vào giao thức đầu cuối | Phạm vi khác dự án hiện tại, ảnh hưởng mọi app; chưa được phép thực hiện |

**Đề xuất kỹ thuật, chưa phải quyết định viết lại:** ưu tiên đường nhập liệu đúng và fail-safe; đo riêng IPC/hàng sự kiện, widget và vẽ màn trên ứng dụng thật; nếu adapter native đem lại cải thiện đã đo thì thay đúng adapter. Không viết lại core chỉ vì nhận định chưa kiểm «mã dùng lại chắc gây chậm». Không giữ phần phụ thuộc có lỗi chỉ vì muốn tái sử dụng. Chưa có bằng chứng bản hiện tại đã tối ưu hoặc bản viết lại chắc chắn tốt hơn.
