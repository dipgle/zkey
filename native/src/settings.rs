// SPDX-License-Identifier: AGPL-3.0-or-later
//! Native preferences, using GTK's system C ABI. No Python or GTK Rust crate.
use crate::ffi::{self as f, Handle};
use std::{
    ffi::{CStr, c_char, c_int},
    panic::{AssertUnwindSafe, catch_unwind},
    ptr,
};
use zkey_native::{
    compose::ToneStyle,
    config::{self, Config, SaveOutcome},
};

#[link(name = "libgtk-3.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn gtk_init_check(argc: *mut c_int, argv: *mut *mut *mut c_char) -> c_int;
    fn gtk_window_new(kind: c_int) -> Handle;
    fn gtk_window_set_title(window: Handle, title: *const c_char);
    fn gtk_window_set_default_size(window: Handle, width: c_int, height: c_int);
    fn gtk_container_set_border_width(container: Handle, border: u32);
    fn gtk_container_add(container: Handle, widget: Handle);
    fn gtk_box_new(orientation: c_int, spacing: c_int) -> Handle;
    fn gtk_box_pack_start(
        container: Handle,
        child: Handle,
        expand: c_int,
        fill: c_int,
        padding: u32,
    );
    fn gtk_check_button_new_with_label(label: *const c_char) -> Handle;
    fn gtk_toggle_button_set_active(button: Handle, active: c_int);
    fn gtk_toggle_button_get_active(button: Handle) -> c_int;
    fn gtk_label_new(label: *const c_char) -> Handle;
    fn gtk_label_set_text(label: Handle, text: *const c_char);
    fn gtk_label_set_line_wrap(label: Handle, wrap: c_int);
    fn gtk_label_set_max_width_chars(label: Handle, width: c_int);
    fn gtk_spin_button_new_with_range(min: f64, max: f64, step: f64) -> Handle;
    fn gtk_spin_button_set_value(spin: Handle, value: f64);
    fn gtk_spin_button_get_value_as_int(spin: Handle) -> c_int;
    fn gtk_button_new_with_label(label: *const c_char) -> Handle;
    fn gtk_widget_show_all(widget: Handle);
    fn gtk_widget_destroy(widget: Handle);
    fn gtk_main();
    fn gtk_main_level() -> u32;
    fn gtk_main_quit();
}
struct View {
    enabled: Handle,
    modern: Handle,
    experimental: Handle,
    webkit: Handle,
    limit: Handle,
    status: Handle,
    path: std::path::PathBuf,
}
fn label_text(label: Handle, text: &str) {
    match f::cstring(text) {
        Ok(text) => unsafe {
            gtk_label_set_text(label, text.as_ptr());
        },
        Err(_) => eprintln!("zkey-native: cannot display settings status"),
    }
}
unsafe extern "C" fn quit(_widget: Handle, _data: Handle) {
    unsafe {
        // A Close click exits the loop; our subsequent widget destruction emits
        // destroy once more. GTK reports a critical if quit is called at level0.
        if gtk_main_level() > 0 {
            gtk_main_quit();
        }
    }
}
unsafe extern "C" fn save(_button: Handle, data: Handle) {
    let outcome = catch_unwind(AssertUnwindSafe(|| -> Result<SaveOutcome, String> {
        let view = unsafe { &*data.cast::<View>() };
        let config = Config {
            enabled: unsafe { gtk_toggle_button_get_active(view.enabled) } != 0,
            style: if unsafe { gtk_toggle_button_get_active(view.modern) } != 0 {
                ToneStyle::Modern
            } else {
                ToneStyle::Traditional
            },
            max_word_keys: unsafe { gtk_spin_button_get_value_as_int(view.limit) } as usize,
            experimental_rewrite: unsafe { gtk_toggle_button_get_active(view.experimental) } != 0,
            webkit_compat: unsafe { gtk_toggle_button_get_active(view.webkit) } != 0,
            ..Config::default()
        };
        config::save(&view.path, &config)
    }))
    .unwrap_or_else(|_| Err("Không lưu được: lỗi nội bộ đã được chặn tại biên giao diện.".into()));
    let view = unsafe { &*data.cast::<View>() };
    let message = match outcome {
        Ok(SaveOutcome::Applied) => {
            "Đã lưu. Kiểu dấu áp dụng khi đổi ô nhập; cầu nối WebKit từ lần mở ứng dụng tiếp theo. Không đổi bộ gõ hệ thống.".into()
        }
        Ok(SaveOutcome::AppliedAuditIncomplete) => {
            "Cấu hình ĐÃ đổi nhưng đồng bộ đĩa/nhật ký chưa đầy đủ. Chưa thể xác nhận lưu bền vững."
                .into()
        }
        Err(error) => format!("Không lưu được: {error}"),
    };
    label_text(view.status, &message);
}
unsafe fn connect(
    widget: Handle,
    signal: &CStr,
    callback: unsafe extern "C" fn(Handle, Handle),
    data: Handle,
) {
    let callback: unsafe extern "C" fn() = unsafe { std::mem::transmute(callback) };
    unsafe {
        f::g_signal_connect_data(widget, signal.as_ptr(), Some(callback), data, None, 0);
    }
}
unsafe fn shell(title: &CStr) -> (Handle, Handle) {
    unsafe {
        let window = gtk_window_new(0);
        f::g_object_ref_sink(window);
        gtk_window_set_title(window, title.as_ptr());
        gtk_window_set_default_size(window, 600, -1);
        let layout = gtk_box_new(1, 12);
        gtk_container_set_border_width(layout, 24);
        gtk_container_add(window, layout);
        connect(window, c"destroy", quit, ptr::null_mut());
        (window, layout)
    }
}
unsafe fn pack(layout: Handle, child: Handle) {
    unsafe {
        gtk_box_pack_start(layout, child, 0, 0, 0);
    }
}
pub fn run() -> Result<(), String> {
    let path = config::path()?;
    let (config, problem) = match Config::load(&path) {
        Ok(c) => (c, None),
        Err(error) => (Config::default(), Some(error)),
    };
    unsafe {
        if gtk_init_check(ptr::null_mut(), ptr::null_mut()) == 0 {
            return Err("Cannot open settings display".into());
        }
        let (window, layout) = shell(c"zkey native — Thiết lập (bản phát triển)");
        let title = gtk_label_new(c"zkey native · Rust độc lập".as_ptr());
        pack(layout, title);
        let enabled = gtk_check_button_new_with_label(c"Cho phép zkey hoạt động".as_ptr());
        let modern = gtk_check_button_new_with_label(
            c"Đặt dấu hiện đại: hoà, thuỷ (tắt: hòa, thủy)".as_ptr(),
        );
        let experimental = gtk_check_button_new_with_label(
            c"Cho phép sửa surrounding thử nghiệm — CHƯA PHÁT HÀNH".as_ptr(),
        );
        let webkit = gtk_check_button_new_with_label(
            c"Cầu nối WebKit GTK3 trong ứng dụng mở riêng (thử nghiệm)".as_ptr(),
        );
        gtk_toggle_button_set_active(enabled, config.enabled.into());
        gtk_toggle_button_set_active(modern, (config.style == ToneStyle::Modern).into());
        gtk_toggle_button_set_active(experimental, config.experimental_rewrite.into());
        gtk_toggle_button_set_active(webkit, config.webkit_compat.into());
        let warning=gtk_label_new(c"Mặc định phím đi nguyên trạng. Đường Telex thử nghiệm có thể nhân chữ trên WebKit; chưa dùng để thay bộ gõ toàn hệ thống. Không lưu nội dung gõ.".as_ptr());
        gtk_label_set_line_wrap(warning, 1);
        gtk_label_set_max_width_chars(warning, 66);
        let limit = gtk_spin_button_new_with_range(8., 256., 1.);
        gtk_spin_button_set_value(limit, config.max_word_keys as f64);
        let status = gtk_label_new(ptr::null());
        gtk_label_set_line_wrap(status, 1);
        gtk_label_set_max_width_chars(status, 66);
        label_text(
            status,
            &match problem {
                Some(error) => {
                    format!("Cấu hình lỗi: {error}. Đang hiện mặc định; chỉ thay khi bấm Lưu.")
                }
                None => "Thiết lập chỉ áp dụng cho bản native; không đụng bản đang cài.".into(),
            },
        );
        let button = gtk_button_new_with_label(c"Lưu thiết lập".as_ptr());
        let mut view = Box::new(View {
            enabled,
            modern,
            experimental,
            webkit,
            limit,
            status,
            path,
        });
        connect(button, c"clicked", save, (&mut *view as *mut View).cast());
        for widget in [
            enabled,
            modern,
            experimental,
            webkit,
            warning,
            gtk_label_new(c"Giới hạn phím một từ (8–256):".as_ptr()),
            limit,
            button,
            status,
        ] {
            pack(layout, widget);
        }
        let close = gtk_button_new_with_label(c"Đóng".as_ptr());
        connect(close, c"clicked", quit, ptr::null_mut());
        pack(layout, close);
        gtk_widget_show_all(window);
        gtk_main();
        gtk_widget_destroy(window);
        f::g_object_unref(window);
    }
    Ok(())
}
pub fn alert(message: &str) -> Result<(), String> {
    let message = f::cstring(message)?;
    unsafe {
        if gtk_init_check(ptr::null_mut(), ptr::null_mut()) == 0 {
            return Err("Cannot open native failure dialog".into());
        }
        let (window, layout) = shell(c"zkey native — Cảnh báo");
        let text = gtk_label_new(message.as_ptr());
        gtk_label_set_line_wrap(text, 1);
        gtk_label_set_max_width_chars(text, 66);
        pack(layout, text);
        let close = gtk_button_new_with_label(c"Đóng".as_ptr());
        connect(close, c"clicked", quit, ptr::null_mut());
        pack(layout, close);
        gtk_widget_show_all(window);
        gtk_main();
        gtk_widget_destroy(window);
        f::g_object_unref(window);
    }
    Ok(())
}
