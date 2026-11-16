// SPDX-License-Identifier: AGPL-3.0-or-later
//! Optional, process-local GTK3/WebKit compatibility bridge. Built as a small
//! cdylib and embedded in the native launcher; NEVER install in ld.so.preload.
//! Uses public C APIs only, weak ownership, no key/text inspection, no layout
//! offsets. GTK4 and non-WebKit fields are forwarded without attachment.
use std::ffi::{CStr, c_char, c_int, c_uint, c_void};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::{ptr, sync::OnceLock};
type H = *mut c_void;
type Filter = unsafe extern "C" fn(H, H) -> c_int;
type GetType = unsafe extern "C" fn() -> usize;
type GetIm = unsafe extern "C" fn(H) -> H;
#[link(name = "libdl.so.2", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn dlsym(handle: H, name: *const c_char) -> H;
}
#[link(name = "libglib-2.0.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn g_timeout_add_full(
        priority: c_int,
        interval: c_uint,
        callback: unsafe extern "C" fn(H) -> c_int,
        data: H,
        destroy: Option<unsafe extern "C" fn(H)>,
    ) -> c_uint;
    fn g_source_remove(id: c_uint) -> c_int;
    fn g_free(memory: H);
}
#[link(name = "libgobject-2.0.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn g_type_check_instance_is_a(instance: H, kind: usize) -> c_int;
    fn g_signal_lookup(name: *const c_char, kind: usize) -> c_uint;
    fn g_signal_has_handler_pending(
        instance: H,
        id: c_uint,
        detail: c_uint,
        may_be_blocked: c_int,
    ) -> c_int;
    fn g_signal_connect_data(
        instance: H,
        signal: *const c_char,
        callback: Option<unsafe extern "C" fn()>,
        data: H,
        destroy: Option<unsafe extern "C" fn(H, H)>,
        flags: c_uint,
    ) -> u64;
    fn g_signal_emit_by_name(instance: H, signal: *const c_char, ...);
    fn g_object_get_data(instance: H, key: *const c_char) -> H;
    fn g_object_set_data_full(
        instance: H,
        key: *const c_char,
        data: H,
        destroy: Option<unsafe extern "C" fn(H)>,
    );
    fn g_object_weak_ref(instance: H, notify: unsafe extern "C" fn(H, H), data: H);
    fn g_object_weak_unref(instance: H, notify: unsafe extern "C" fn(H, H), data: H);
    fn g_object_ref(instance: H) -> H;
    fn g_object_unref(instance: H);
    fn g_object_get(instance: H, first_property: *const c_char, ...);
}
// Do not link GTK3/GDK3 into the preload: that would break GTK4 applications
// before the first key. Resolve only APIs already loaded by the target itself.
unsafe fn symbol<T: Copy>(name: &CStr) -> Option<T> {
    unsafe {
        let pointer = dlsym(ptr::null_mut(), name.as_ptr());
        if pointer.is_null() {
            None
        } else {
            assert_eq!(std::mem::size_of::<T>(), std::mem::size_of::<H>());
            Some(std::mem::transmute_copy(&pointer))
        }
    }
}
struct Binding {
    im: H,
    refresh: c_uint,
}
unsafe extern "C" fn release_context(context: H) {
    unsafe {
        g_object_unref(context);
    }
}
unsafe extern "C" fn refresh(context: H) -> c_int {
    if catch_unwind(AssertUnwindSafe(|| unsafe {
        let binding = g_object_get_data(context, c"zkey-public-webkit-delete-bridge-v1".as_ptr())
            .cast::<Binding>();
        if binding.is_null() {
            return;
        }
        (*binding).refresh = 0;
        if !(*binding).im.is_null() {
            let mut purpose: c_int = 0;
            let mut hints: c_uint = 0;
            g_object_get(
                context,
                c"input-purpose".as_ptr(),
                &mut purpose,
                c"input-hints".as_ptr(),
                &mut hints,
                ptr::null::<c_char>(),
            );
            if !(0..=7).contains(&purpose) || hints & ((1 << 11) | (1 << 12)) != 0 {
                return;
            }
            // Use the public GET operation, not a naked signal emission: GTK
            // installs a temporary retrieval frame around its signal handler.
            // Forward that actual application snapshot into the public SET
            // operation so the IBus slave transmits the post-burst document.
            // Never use libibus's optimistic cached text or log these bytes.
            let Some(get) = symbol::<
                unsafe extern "C" fn(H, *mut *mut c_char, *mut c_int) -> c_int,
            >(c"gtk_im_context_get_surrounding") else {
                return;
            };
            let Some(set) = symbol::<unsafe extern "C" fn(H, *const c_char, c_int, c_int)>(
                c"gtk_im_context_set_surrounding",
            ) else {
                return;
            };
            let mut text = ptr::null_mut();
            let mut cursor = 0;
            let obtained = get(context, &mut text, &mut cursor);
            if std::env::var_os("ZKEY_NATIVE_TRACE").is_some(){eprintln!("zkey-webkit-bridge: live surrounding query obtained={}",obtained!=0);}
            if !text.is_null() {
                if obtained != 0 && CStr::from_ptr(text).to_bytes().len() <= 1_048_576 {
                    set(context, text, -1, cursor);
                }
                g_free(text.cast());
            }
        }
    }))
    .is_err()
    {
        fatal();
    }
    0
}
unsafe fn schedule_refresh(context: H) {
    unsafe {
        let binding = g_object_get_data(context, c"zkey-public-webkit-delete-bridge-v1".as_ptr())
            .cast::<Binding>();
        if binding.is_null() || (*binding).im.is_null() {
            return;
        }
        if (*binding).refresh != 0 {
            g_source_remove((*binding).refresh);
        }
        // One nominal display-frame idle debounce; it does not authorize an edit.
        // The engine still requires exact content/caret confirmation and a bound.
        g_object_ref(context);
        (*binding).refresh = g_timeout_add_full(0, 16, refresh, context, Some(release_context));
        if (*binding).refresh == 0 {
            g_object_unref(context);
            fatal();
        }
    }
}
unsafe extern "C" fn gone(data: H, _object: H) {
    unsafe {
        (*data.cast::<Binding>()).im = ptr::null_mut();
    }
}
unsafe extern "C" fn drop_binding(data: H) {
    unsafe {
        let binding = Box::from_raw(data.cast::<Binding>());
        if !binding.im.is_null() {
            g_object_weak_unref(binding.im, gone, data);
        }
    }
}
fn fatal() -> ! {
    eprintln!("zkey-webkit-bridge: fatal compatibility error (input omitted)");
    std::process::abort()
}
unsafe extern "C" fn forward(_gtk: H, offset: c_int, count: c_uint, data: H) -> c_int {
    catch_unwind(AssertUnwindSafe(|| unsafe {
        let im = (*data.cast::<Binding>()).im;
        if im.is_null() {
            return 0;
        }
        g_object_ref(im);
        g_signal_emit_by_name(im, c"delete-surrounding".as_ptr(), offset, count);
        g_object_unref(im);
        1
    }))
    .unwrap_or_else(|_| fatal())
}
unsafe fn attach(context: H, event: H) {
    unsafe {
        let Some(major) = symbol::<unsafe extern "C" fn() -> c_uint>(c"gtk_get_major_version")
        else {
            return;
        };
        if major() != 3 || context.is_null() || event.is_null() {
            return;
        }
        let Some(multitype) = symbol::<GetType>(c"gtk_im_multicontext_get_type") else {
            return;
        };
        if g_type_check_instance_is_a(context, multitype()) == 0 {
            return;
        }
        let Some(kind) = symbol::<GetType>(c"webkit_web_view_get_type") else {
            return;
        };
        let Some(get) = symbol::<GetIm>(c"webkit_web_view_get_input_method_context") else {
            return;
        };
        let Some(event_window) = symbol::<unsafe extern "C" fn(H) -> H>(c"gdk_event_get_window")
        else {
            return;
        };
        let Some(user_data) =
            symbol::<unsafe extern "C" fn(H, *mut H)>(c"gdk_window_get_user_data")
        else {
            return;
        };
        let Some(top_level) = symbol::<unsafe extern "C" fn(H) -> H>(c"gtk_widget_get_toplevel")
        else {
            return;
        };
        let Some(window_type) = symbol::<GetType>(c"gtk_window_get_type") else {
            return;
        };
        let Some(focus) = symbol::<unsafe extern "C" fn(H) -> H>(c"gtk_window_get_focus") else {
            return;
        };
        let window = event_window(event);
        if window.is_null() {
            return;
        }
        let mut widget = ptr::null_mut();
        user_data(window, &mut widget);
        if widget.is_null() {
            return;
        }
        if g_type_check_instance_is_a(widget, kind()) == 0 {
            let top = top_level(widget);
            if top.is_null() || g_type_check_instance_is_a(top, window_type()) == 0 {
                return;
            }
            widget = focus(top);
            if widget.is_null() || g_type_check_instance_is_a(widget, kind()) == 0 {
                return;
            }
        }
        let im = get(widget);
        if im.is_null() {
            return;
        }
        let key = c"zkey-public-webkit-delete-bridge-v1";
        let previous = g_object_get_data(context, key.as_ptr()).cast::<Binding>();
        if !previous.is_null() {
            if (*previous).im != im {
                if !(*previous).im.is_null() {
                    g_object_weak_unref((*previous).im, gone, previous.cast());
                }
                (*previous).im = im;
                g_object_weak_ref(im, gone, previous.cast());
            }
            return;
        }
        let signal = g_signal_lookup(c"delete-surrounding".as_ptr(), multitype());
        // On a corrected WebKit build, its existing handler wins; don't double-edit.
        if signal == 0 || g_signal_has_handler_pending(context, signal, 0, 1) != 0 {
            return;
        }
        let data = Box::into_raw(Box::new(Binding { im, refresh: 0 })).cast();
        g_object_weak_ref(im, gone, data);
        g_object_set_data_full(context, key.as_ptr(), data, Some(drop_binding));
        let callback: unsafe extern "C" fn() =
            std::mem::transmute(forward as unsafe extern "C" fn(H, c_int, c_uint, H) -> c_int);
        if g_signal_connect_data(
            context,
            c"delete-surrounding".as_ptr(),
            Some(callback),
            data,
            None,
            0,
        ) == 0
        {
            fatal();
        }
        eprintln!("zkey-webkit-bridge: missing public GTK3-to-WebKit deletion callback attached");
    }
}
#[unsafe(no_mangle)]
/// Forward the public GTK filter and, for an opted-in GTK3/WebKit view, bridge
/// its missing delete callback. No ABI parameters or return values are changed.
///
/// # Safety
/// Called by GTK with a valid live GtkIMContext and the matching Gdk event on
/// its UI thread, following gtk_im_context_filter_keypress's public contract.
pub unsafe extern "C" fn gtk_im_context_filter_keypress(context: H, event: H) -> c_int {
    static NEXT: OnceLock<usize> = OnceLock::new();
    let address = *NEXT.get_or_init(|| unsafe {
        dlsym((-1isize) as H, c"gtk_im_context_filter_keypress".as_ptr()) as usize
    });
    if address == 0 {
        fatal();
    }
    unsafe {
        g_object_ref(context);
    }
    if catch_unwind(AssertUnwindSafe(|| unsafe { attach(context, event) })).is_err() {
        fatal();
    }
    let original: Filter = unsafe { std::mem::transmute(address) };
    let result = unsafe { original(context, event) };
    if catch_unwind(AssertUnwindSafe(|| unsafe { schedule_refresh(context) })).is_err() {
        fatal();
    }
    unsafe {
        g_object_unref(context);
    }
    result
}
