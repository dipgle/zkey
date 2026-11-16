// SPDX-License-Identifier: AGPL-3.0-or-later
//! Minimal bindings to PUBLIC system C APIs. No generated/vendored crate.
//! Opaque handles stay on GLib's main thread. Rust-owned callbacks catch unwind.
use std::ffi::{CStr, CString, c_char, c_int, c_uint, c_void};
use std::ptr;

pub type Handle = *mut c_void;
pub type Method = unsafe extern "C" fn(
    Handle,
    *const c_char,
    *const c_char,
    *const c_char,
    *const c_char,
    Handle,
    Handle,
    Handle,
);
pub type GetProperty = unsafe extern "C" fn(
    Handle,
    *const c_char,
    *const c_char,
    *const c_char,
    *const c_char,
    *mut Handle,
    Handle,
) -> Handle;
pub type SetProperty = unsafe extern "C" fn(
    Handle,
    *const c_char,
    *const c_char,
    *const c_char,
    *const c_char,
    Handle,
    *mut Handle,
    Handle,
) -> c_int;

#[repr(C)]
pub struct VTable {
    pub method: Option<Method>,
    pub get: Option<GetProperty>,
    pub set: Option<SetProperty>,
    pub padding: [Handle; 8],
}
// Immutable function table; its raw reserved pointers are all null.
unsafe impl Sync for VTable {}

#[link(name = "libglib-2.0.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    pub fn g_main_loop_new(context: Handle, running: c_int) -> Handle;
    pub fn g_main_loop_run(main_loop: Handle);
    pub fn g_main_loop_quit(main_loop: Handle);
    pub fn g_main_loop_unref(main_loop: Handle);
    pub fn g_error_free(error: Handle);
    fn g_variant_ref_sink(value: Handle) -> Handle;
    fn g_variant_unref(value: Handle);
    fn g_variant_new_object_path(value: *const c_char) -> Handle;
    fn g_variant_new_string(value: *const c_char) -> Handle;
    fn g_variant_new_dict_entry(key: Handle, value: Handle) -> Handle;
    fn g_variant_new_array(kind: *const c_void, children: *const Handle, length: usize) -> Handle;
    fn g_variant_new_boolean(value: c_int) -> Handle;
    fn g_variant_new_uint32(value: c_uint) -> Handle;
    fn g_variant_new_int32(value: i32) -> Handle;
    fn g_variant_new_variant(value: Handle) -> Handle;
    fn g_variant_new_tuple(children: *const Handle, length: usize) -> Handle;
    fn g_variant_get_child_value(value: Handle, index: usize) -> Handle;
    fn g_variant_n_children(value: Handle) -> usize;
    fn g_variant_get_variant(value: Handle) -> Handle;
    fn g_variant_get_uint32(value: Handle) -> c_uint;
    fn g_variant_get_string(value: Handle, length: *mut usize) -> *const c_char;
    fn g_variant_get_type_string(value: Handle) -> *const c_char;
}
#[link(name = "libgobject-2.0.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    pub fn g_bus_get_sync(kind: c_int, cancellable: Handle, error: *mut Handle) -> Handle;
    pub fn g_dbus_connection_call_sync(
        conn: Handle,
        name: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        method: *const c_char,
        parameters: Handle,
        reply_type: *const c_void,
        flags: u32,
        timeout: i32,
        cancellable: Handle,
        error: *mut Handle,
    ) -> Handle;
    pub fn g_object_ref_sink(object: Handle) -> Handle;
    pub fn g_object_unref(object: Handle);
    pub fn g_signal_connect_data(
        instance: Handle,
        signal: *const c_char,
        callback: Option<unsafe extern "C" fn()>,
        data: Handle,
        destroy: Option<unsafe extern "C" fn(Handle, Handle)>,
        flags: u32,
    ) -> u64;
}
#[link(name = "libgio-2.0.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    pub fn g_dbus_node_info_new_for_xml(xml: *const c_char, error: *mut Handle) -> Handle;
    pub fn g_dbus_node_info_lookup_interface(node: Handle, name: *const c_char) -> Handle;
    pub fn g_dbus_node_info_unref(node: Handle);
    pub fn g_dbus_connection_register_object(
        conn: Handle,
        path: *const c_char,
        interface: Handle,
        vtable: *const VTable,
        data: Handle,
        destroy: Option<unsafe extern "C" fn(Handle)>,
        error: *mut Handle,
    ) -> u32;
    pub fn g_dbus_connection_unregister_object(conn: Handle, id: u32) -> c_int;
    pub fn g_dbus_connection_emit_signal(
        conn: Handle,
        destination: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        signal: *const c_char,
        parameters: Handle,
        error: *mut Handle,
    ) -> c_int;
    pub fn g_dbus_method_invocation_return_value(invocation: Handle, value: Handle);
    pub fn g_dbus_method_invocation_return_dbus_error(
        invocation: Handle,
        name: *const c_char,
        message: *const c_char,
    );
    pub fn g_dbus_connection_flush_sync(
        conn: Handle,
        cancellable: Handle,
        error: *mut Handle,
    ) -> c_int;
}
#[link(name = "libibus-1.0.so.5", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    pub fn ibus_init();
    pub fn ibus_bus_new() -> Handle;
    pub fn ibus_bus_is_connected(bus: Handle) -> c_int;
    pub fn ibus_bus_get_connection(bus: Handle) -> Handle;
    pub fn ibus_bus_set_global_engine(bus: Handle, name: *const c_char) -> c_int;
    pub fn ibus_bus_register_component(bus: Handle, component: Handle) -> c_int;
    pub fn ibus_component_new(
        name: *const c_char,
        description: *const c_char,
        version: *const c_char,
        license: *const c_char,
        author: *const c_char,
        homepage: *const c_char,
        command: *const c_char,
        domain: *const c_char,
    ) -> Handle;
    pub fn ibus_engine_desc_new(
        name: *const c_char,
        longname: *const c_char,
        description: *const c_char,
        language: *const c_char,
        license: *const c_char,
        author: *const c_char,
        icon: *const c_char,
        layout: *const c_char,
    ) -> Handle;
    pub fn ibus_component_add_engine(component: Handle, engine: Handle);
    fn ibus_text_new_from_string(text: *const c_char) -> Handle;
    fn ibus_serializable_serialize_object(object: Handle) -> Handle;
}

pub fn cstring(value: &str) -> Result<CString, String> {
    CString::new(value)
        .map_err(|_| "Unexpected NUL in system API argument (contents omitted)".into())
}

pub struct Variant(pub Handle);
impl Drop for Variant {
    fn drop(&mut self) {
        unsafe {
            g_variant_unref(self.0);
        }
    }
}
impl Variant {
    // SAFETY: constructors below return non-null floating variants. Sink once.
    fn new(value: Handle) -> Self {
        Self(unsafe { g_variant_ref_sink(value) })
    }
    pub fn tuple(items: &[Self]) -> Self {
        let pointers: Vec<_> = items.iter().map(|item| item.0).collect();
        Self::new(unsafe { g_variant_new_tuple(pointers.as_ptr(), pointers.len()) })
    }
    pub fn boolean(value: bool) -> Self {
        Self::new(unsafe { g_variant_new_boolean(value.into()) })
    }
    pub fn u32(value: u32) -> Self {
        Self::new(unsafe { g_variant_new_uint32(value) })
    }
    pub fn i32(value: i32) -> Self {
        Self::new(unsafe { g_variant_new_int32(value) })
    }
    pub fn path(value: &str) -> Result<Self, String> {
        let v = cstring(value)?;
        Ok(Self::new(unsafe { g_variant_new_object_path(v.as_ptr()) }))
    }
    pub fn string(value: &str) -> Result<Self, String> {
        let v = cstring(value)?;
        Ok(Self::new(unsafe { g_variant_new_string(v.as_ptr()) }))
    }
    pub fn dictionary(items: &[(String, String)]) -> Result<Self, String> {
        if items.is_empty() {
            return Err("Activation dictionary cannot be empty".into());
        }
        let mut entries = Vec::new();
        for (key, value) in items {
            let key = Self::string(key)?;
            let value = Self::string(value)?;
            entries.push(Self::new(unsafe {
                g_variant_new_dict_entry(key.0, value.0)
            }));
        }
        let pointers: Vec<_> = entries.iter().map(|v| v.0).collect();
        Ok(Self::new(unsafe {
            g_variant_new_array(ptr::null(), pointers.as_ptr(), pointers.len())
        }))
    }
    pub fn boxed(value: &Self) -> Self {
        Self::new(unsafe { g_variant_new_variant(value.0) })
    }
    pub fn text(value: &str) -> Result<Self, String> {
        let v = cstring(value)?;
        unsafe {
            let object = ibus_text_new_from_string(v.as_ptr());
            if object.is_null() {
                return Err("IBus.Text allocation failed".into());
            }
            g_object_ref_sink(object);
            let serialized = ibus_serializable_serialize_object(object);
            g_object_unref(object);
            if serialized.is_null() {
                return Err("IBus.Text serialization failed".into());
            }
            let serialized = Self::new(serialized);
            Ok(Self::boxed(&serialized))
        }
    }
    pub fn kind(&self) -> String {
        unsafe {
            CStr::from_ptr(g_variant_get_type_string(self.0))
                .to_string_lossy()
                .into_owned()
        }
    }
    pub fn child(&self, index: usize) -> Result<Self, String> {
        if unsafe { g_variant_n_children(self.0) } <= index {
            return Err("Malformed D-Bus tuple".into());
        }
        Ok(Self(unsafe { g_variant_get_child_value(self.0, index) }))
    }
    pub fn as_u32(&self) -> Result<u32, String> {
        if self.kind() != "u" {
            return Err("Expected uint32 D-Bus argument".into());
        }
        Ok(unsafe { g_variant_get_uint32(self.0) })
    }
    pub fn as_string(&self) -> Result<String, String> {
        if !matches!(self.kind().as_str(), "s" | "o") {
            return Err("Expected string D-Bus argument".into());
        }
        Ok(unsafe {
            CStr::from_ptr(g_variant_get_string(self.0, ptr::null_mut()))
                .to_string_lossy()
                .into_owned()
        })
    }
    pub fn as_text(&self) -> Result<String, String> {
        if self.kind() != "v" {
            return Err("Expected IBus.Text variant".into());
        }
        unsafe {
            let wrapped = Self(g_variant_get_variant(self.0));
            // Decode only the documented Text wire tuple. Never instantiate an
            // arbitrary GObject type supplied by a client or deserialize its
            // unneeded attributes/attachments through an unchecked C API.
            if wrapped.kind() != "(sa{sv}sv)" || wrapped.child(0)?.as_string()? != "IBusText" {
                return Err("Surrounding argument is not a valid IBus.Text tuple".into());
            }
            wrapped.child(2)?.as_string()
        }
    }
}

/// Borrow a GVariant temporarily without taking/dropping the C caller's ref.
pub unsafe fn borrowed(value: Handle) -> std::mem::ManuallyDrop<Variant> {
    std::mem::ManuallyDrop::new(Variant(value))
}

pub fn error_message(error: Handle, stage: &str) -> String {
    if !error.is_null() {
        unsafe {
            g_error_free(error);
        }
    }
    format!("{stage} failed (system error details omitted to avoid input disclosure)")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn system_text_wire_roundtrip_and_wrong_type_rejection() {
        unsafe {
            ibus_init();
        }
        assert_eq!(
            Variant::text("tiếng 🙂").unwrap().as_text().unwrap(),
            "tiếng 🙂"
        );
        let wrong = Variant::boxed(&Variant::string("not an IBus object").unwrap());
        assert!(wrong.as_text().is_err());
        assert!(Variant::u32(1).as_text().is_err());
    }
    #[test]
    fn dictionary_and_scalar_types_match_the_public_dbus_contract() {
        assert_eq!(
            Variant::dictionary(&[("A".into(), "B".into())])
                .unwrap()
                .kind(),
            "a{ss}"
        );
        assert!(Variant::dictionary(&[]).is_err());
        assert!(Variant::boolean(true).as_u32().is_err());
    }
}
