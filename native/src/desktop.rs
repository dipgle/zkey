// SPDX-License-Identifier: AGPL-3.0-or-later
//! IBus service over GIO's public D-Bus API, with no GObject subclass offsets.
use crate::ffi::{self as f, Handle, VTable, Variant};
use std::{
    ffi::{CStr, c_char, c_int},
    panic::{AssertUnwindSafe, catch_unwind},
    path::Path,
    ptr,
};
use zkey_native::{
    config::{self, Config},
    session::{Edit, Session},
};

const FACTORY: &CStr = c"org.freedesktop.IBus.Factory";
const ENGINE: &CStr = c"org.freedesktop.IBus.Engine";
const SERVICE: &CStr = c"org.freedesktop.IBus.Service";

struct Instance {
    conn: Handle,
    path: std::ffi::CString,
    state: Session,
    requested: bool,
    ctrl: bool,
    retired: bool,
    registrations: Vec<u32>,
    trace: bool,
    experimental: bool,
    latest_type: Option<(u32, u32)>,
}
struct Application {
    conn: Handle,
    node: Handle,
    registrations: Vec<u32>,
    instances: Vec<InstanceBox>,
    experimental: bool,
    next_id: u64,
    config: Config,
}
// Stable addresses are required by GIO; the wrapper documents intentional boxes.
struct InstanceBox(Box<Instance>);

fn emit(instance: &Instance, name: &CStr, values: &[Variant]) -> Result<(), String> {
    let params = Variant::tuple(values);
    let mut error = ptr::null_mut();
    let ok = unsafe {
        f::g_dbus_connection_emit_signal(
            instance.conn,
            ptr::null(),
            instance.path.as_ptr(),
            ENGINE.as_ptr(),
            name.as_ptr(),
            params.0,
            &mut error,
        )
    };
    if ok == 0 {
        Err(f::error_message(error, "IBus signal emission"))
    } else {
        Ok(())
    }
}
fn apply(instance: &Instance, edit: Edit) -> Result<bool, String> {
    if edit.remove > 0 {
        emit(
            instance,
            c"DeleteSurroundingText",
            &[
                Variant::i32(-(edit.remove as i32)),
                Variant::u32(edit.remove),
            ],
        )?;
    }
    if !edit.insert.is_empty() {
        emit(instance, c"CommitText", &[Variant::text(&edit.insert)?])?;
    }
    Ok(edit.handled)
}
fn clear_preedit(instance: &Instance) -> Result<(), String> {
    emit(
        instance,
        c"UpdatePreeditText",
        &[
            Variant::text("")?,
            Variant::u32(0),
            Variant::boolean(false),
            Variant::u32(0),
        ],
    )
}
fn key(instance: &mut Instance, value: u32, state: u32) -> Result<bool, String> {
    const RELEASE: u32 = 1 << 30;
    if matches!(value, 0xffe3 | 0xffe4) {
        if state & RELEASE != 0 {
            if instance.ctrl {
                instance.state.freeze();
            }
            instance.ctrl = false;
        } else {
            instance.ctrl = true;
        }
        return Ok(false);
    }
    if state & RELEASE != 0 {
        return Ok(false);
    }
    instance.ctrl = false;
    if matches!(value, 0xffe1 | 0xffe2 | 0xffe5) {
        return Ok(false);
    }
    if state & ((1 << 2) | (1 << 3) | (1 << 7) | (1 << 26) | (1 << 27) | (1 << 28)) != 0 {
        instance.state.reset();
        return Ok(false);
    }
    if !instance.state.accepts() {
        return Ok(false);
    }
    if !instance.requested {
        emit(instance, c"RequireSurroundingText", &[])?;
        instance.requested = true;
    }
    if value == 0xff08 {
        instance.state.backspace();
        return Ok(false);
    }
    if value == 0xff1b {
        let edit = instance.state.escape();
        return apply(instance, edit);
    }
    let unicode = if value & 0xff00_0000 == 0x0100_0000 {
        value & 0x00ff_ffff
    } else {
        value
    };
    if let Some(c) = char::from_u32(unicode)
        .filter(|c| !c.is_control() && (*c as u32 <= 255 || value & 0xff00_0000 == 0x0100_0000))
    {
        let edit = instance.state.key(c);
        apply(instance, edit)
    } else {
        instance.state.reset();
        Ok(false)
    }
}
fn answer(invocation: Handle, result: Result<Variant, String>) {
    match result {
        Ok(reply) => unsafe { f::g_dbus_method_invocation_return_value(invocation, reply.0) },
        Err(_) => {
            // Do not include GVariant arguments, key values or typed text.
            eprintln!("zkey-native: desktop request failed; composition not certified");
            unsafe {
                f::g_dbus_method_invocation_return_dbus_error(
                    invocation,
                    c"org.freedesktop.DBus.Error.Failed".as_ptr(),
                    c"zkey-native desktop operation failed (input omitted)".as_ptr(),
                );
            }
        }
    }
}
fn export(
    app: &mut Application,
    path: &CStr,
    interface: &CStr,
    table: &VTable,
    data: Handle,
) -> Result<u32, String> {
    let info = unsafe { f::g_dbus_node_info_lookup_interface(app.node, interface.as_ptr()) };
    if info.is_null() {
        return Err("Missing native interface schema".into());
    }
    let mut error = ptr::null_mut();
    let id = unsafe {
        f::g_dbus_connection_register_object(
            app.conn,
            path.as_ptr(),
            info,
            table,
            data,
            None,
            &mut error,
        )
    };
    if id == 0 {
        return Err(f::error_message(error, "D-Bus object export"));
    }
    app.registrations.push(id);
    Ok(id)
}
unsafe extern "C" fn factory(
    _conn: Handle,
    _sender: *const c_char,
    _path: *const c_char,
    _interface: *const c_char,
    method: *const c_char,
    params: Handle,
    invocation: Handle,
    data: Handle,
) {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<Variant, String> {
        let app = unsafe { &mut *data.cast::<Application>() };
        let method = unsafe { CStr::from_ptr(method) };
        if method != c"CreateEngine" {
            return Err("Unknown factory method".into());
        }
        let params = unsafe { f::borrowed(params) };
        if params.child(0)?.as_string()? != "zkey-native" {
            return Err("Unknown engine".into());
        }
        // Destroyed contexts are reclaimed at the next factory request, outside
        // their own callback. Do not retain words or leak one box per focus.
        for i in (0..app.instances.len()).rev() {
            if app.instances[i].0.retired {
                let old = app.instances.remove(i);
                for id in &old.0.registrations {
                    unsafe {
                        f::g_dbus_connection_unregister_object(app.conn, *id);
                    }
                    app.registrations.retain(|registered| registered != id);
                }
            }
        }
        // Explicit bound, reported as a failure, never silently evict a context.
        if app.instances.len() >= 256 {
            return Err("Native context bound reached; restart private test session".into());
        }
        app.next_id = app
            .next_id
            .checked_add(1)
            .ok_or("Engine identifier space exhausted")?;
        let path = format!("/org/freedesktop/IBus/Engine/Native{}", app.next_id);
        let mut instance = Box::new(Instance {
            conn: app.conn,
            path: f::cstring(&path)?,
            state: Session::new(
                app.config.style,
                app.config.enabled,
                app.config.max_word_keys,
                app.experimental || app.config.experimental_rewrite,
            ),
            requested: false,
            ctrl: false,
            retired: false,
            registrations: Vec::new(),
            trace: std::env::var_os("ZKEY_NATIVE_TRACE").is_some(),
            experimental: app.experimental,
            latest_type: None,
        });
        let pointer = (&mut *instance as *mut Instance).cast();
        let cpath = f::cstring(&path)?;
        instance
            .registrations
            .push(export(app, &cpath, ENGINE, &ENGINE_VTABLE, pointer)?);
        // Keep data alive even if the second export fails.
        app.instances.push(InstanceBox(instance));
        let service_id = export(app, &cpath, SERVICE, &ENGINE_VTABLE, pointer)?;
        app.instances
            .last_mut()
            .ok_or("Missing engine instance")?
            .0
            .registrations
            .push(service_id);
        eprintln!("zkey-native: context registered");
        Ok(Variant::tuple(&[Variant::path(&path)?]))
    }))
    .unwrap_or_else(|_| Err("Panic contained at factory ABI boundary".into()));
    answer(invocation, result);
}
unsafe extern "C" fn engine(
    _conn: Handle,
    _sender: *const c_char,
    _path: *const c_char,
    _interface: *const c_char,
    method: *const c_char,
    params: Handle,
    invocation: Handle,
    data: Handle,
) {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<Variant, String> {
        let instance = unsafe { &mut *data.cast::<Instance>() };
        let method = unsafe { CStr::from_ptr(method) }.to_bytes();
        let params = unsafe { f::borrowed(params) };
        if instance.retired {
            return Err("Engine context already destroyed".into());
        }
        match method {
            b"ProcessKeyEvent" => {
                let handled = key(
                    instance,
                    params.child(0)?.as_u32()?,
                    params.child(2)?.as_u32()?,
                )?;
                if instance.trace {
                    eprintln!(
                        "zkey-native: key-event handled={handled} protected={}",
                        instance.state.protected()
                    );
                }
                Ok(Variant::tuple(&[Variant::boolean(handled)]))
            }
            b"SetCapabilities" => {
                instance.state.capabilities(params.child(0)?.as_u32()?);
                Ok(Variant::tuple(&[]))
            }
            b"SetSurroundingText" => {
                if instance.trace{eprintln!("zkey-native: surrounding-event protected={}",instance.state.protected());}
                if !instance.state.protected() {
                    let text = params.child(0)?.as_text()?;
                    if text.len() > 1_048_576 {
                        instance.state.reset();
                        return Err("Surrounding payload exceeds safety bound".into());
                    }
                    let edit = instance.state.snapshot(
                        &text,
                        params.child(1)?.as_u32()? as usize,
                        params.child(2)?.as_u32()? as usize,
                    );
                    apply(instance, edit)?;
                }
                Ok(Variant::tuple(&[]))
            }
            b"FocusIn" | b"FocusInId" | b"FocusOut" | b"FocusOutId" | b"Reset" | b"Disable"
            | b"Enable" | b"Destroy" => {
                if matches!(method, b"FocusIn" | b"FocusInId") {
                    match config::path().and_then(|path| Config::load(&path)) {
                        Ok(config) => {
                            instance.state.configure(&config, instance.experimental);
                            settings_status(false)?;
                        },
                        Err(_) => {
                            // A corrupt/incomplete settings transaction must not
                            // silently keep an older 'enabled' decision alive.
                            instance.state.enabled=false;
                            instance.state.reset();
                            eprintln!("zkey-native: settings invalid; composition bypassed until valid settings are restored");
                            settings_status(true)?;
                        },
                    }
                }
                if method == b"Reset" {
                    instance.state.client_reset();
                } else {
                    instance.state.reset();
                }
                instance.ctrl = false;
                instance.requested = false;
                if matches!(method, b"FocusIn" | b"FocusInId") {
                    // IBus caches ContentType on the engine and need not resend
                    // an unchanged value when it changes input-context IDs.
                    // Never guess a per-ID purpose from the client name. This
                    // cannot protect a client that fails to declare a secret.
                    if let Some((purpose, hints)) = instance.latest_type {
                        instance.state.content(purpose, hints);
                    } else {
                        instance.state.leave_context();
                    }
                }
                if matches!(
                    method,
                    b"FocusOut" | b"FocusOutId" | b"Disable" | b"Destroy"
                ) {
                    instance.state.leave_context();
                }
                if instance.trace {
                    eprintln!(
                        "zkey-native: context-state event={} protected={}",
                        String::from_utf8_lossy(method),
                        instance.state.protected()
                    );
                }
                if method == b"Destroy" {
                    instance.retired = true;
                }
                clear_preedit(instance)?;
                Ok(Variant::tuple(&[]))
            }
            b"SetCursorLocation" | b"PropertyActivate" | b"PropertyShow" | b"PropertyHide"
            | b"PageUp" | b"PageDown" | b"CursorUp" | b"CursorDown" => Ok(Variant::tuple(&[])),
            _ => Err("Unsupported native engine method".into()),
        }
    }))
    .unwrap_or_else(|_| Err("Panic contained at engine ABI boundary".into()));
    answer(invocation, result);
}

fn settings_status(invalid: bool) -> Result<(), String> {
    // The private launcher observes metadata only, never typed text. It owns
    // the root and turns this health state into a visible, dismissible alert.
    if let Some(root) = std::env::var_os("ZKEY_NATIVE_SESSION_ROOT") {
        let marker = Path::new(&root).join("settings-invalid");
        if invalid {
            std::fs::write(marker, b"configuration rejected; composition bypassed\n")
                .map_err(|_| "Cannot signal invalid native settings to the supervisor")?;
        } else {
            match std::fs::remove_file(marker) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(_) => return Err("Cannot clear native settings failure status".into()),
            }
        }
    }
    Ok(())
}
unsafe extern "C" fn get_property(
    _conn: Handle,
    _sender: *const c_char,
    _path: *const c_char,
    _interface: *const c_char,
    name: *const c_char,
    _error: *mut Handle,
    _data: Handle,
) -> Handle {
    match catch_unwind(AssertUnwindSafe(|| {
        let name = unsafe { CStr::from_ptr(name) }.to_bytes();
        // ActiveSurroundingText=true makes IBus request surrounding eagerly on
        // focus, even from VTE which has no retrieve-surrounding implementation.
        // Ask explicitly in key() only after capability + content gates pass.
        let value = Variant::boolean(name == b"FocusId");
        let handle = value.0;
        std::mem::forget(value);
        handle
    })) {
        Ok(value) => value,
        Err(_) => ptr::null_mut(),
    }
}
unsafe extern "C" fn set_property(
    _conn: Handle,
    _sender: *const c_char,
    _path: *const c_char,
    _interface: *const c_char,
    name: *const c_char,
    value: Handle,
    _error: *mut Handle,
    data: Handle,
) -> c_int {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        if unsafe { CStr::from_ptr(name) } != c"ContentType" {
            return Err("Unknown property".into());
        }
        let instance = unsafe { &mut *data.cast::<Instance>() };
        let value = unsafe { f::borrowed(value) };
        let purpose = value.child(0)?.as_u32()?;
        let hints = value.child(1)?.as_u32()?;
        instance.state.content(purpose, hints);
        instance.latest_type = Some((purpose, hints));
        if instance.trace {
            eprintln!(
                "zkey-native: content-type purpose={purpose} protected={}",
                instance.state.protected()
            );
        }
        if instance.state.protected() {
            clear_preedit(instance)?;
        }
        Ok(())
    }));
    i32::from(matches!(result, Ok(Ok(()))))
}
static FACTORY_VTABLE: VTable = VTable {
    method: Some(factory),
    get: None,
    set: None,
    padding: [ptr::null_mut(); 8],
};
static ENGINE_VTABLE: VTable = VTable {
    method: Some(engine),
    get: Some(get_property),
    set: Some(set_property),
    padding: [ptr::null_mut(); 8],
};

fn verify_private_environment() -> Result<(), String> {
    let root = match std::env::var_os("ZKEY_NATIVE_SESSION_ROOT") {
        Some(path) => {
            let root = Path::new(&path)
                .canonicalize()
                .map_err(|_| "Private native session is unavailable")?;
            if !root
                .file_name()
                .is_some_and(|s| s.to_string_lossy().starts_with("zn-"))
            {
                return Err("Invalid native session root".into());
            }
            root
        }
        None => Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .ok_or("Missing project directory")?
            .join(".tmp")
            .canonicalize()
            .map_err(|_| "Missing private scratch directory")?,
    };
    let runtime = std::env::var("XDG_RUNTIME_DIR").map_err(|_| "Missing private runtime")?;
    let runtime = Path::new(&runtime)
        .canonicalize()
        .map_err(|_| "Private runtime unavailable")?;
    let address = std::env::var("IBUS_ADDRESS").map_err(|_| "Missing private IBus address")?;
    let socket = address
        .strip_prefix("unix:path=")
        .ok_or("Only a private filesystem IBus socket is allowed")?;
    let socket = Path::new(socket)
        .canonicalize()
        .map_err(|_| "Private IBus socket unavailable")?;
    let session_bus =
        std::env::var("DBUS_SESSION_BUS_ADDRESS").map_err(|_| "Missing private session bus")?;
    let session_path = session_bus
        .split(',')
        .next()
        .and_then(|s| s.strip_prefix("unix:path="))
        .ok_or("Only a private filesystem session bus is allowed")?;
    let session_path = Path::new(session_path)
        .canonicalize()
        .map_err(|_| "Private session bus unavailable")?;
    if runtime == root || !runtime.starts_with(&root) || !socket.starts_with(&root) {
        return Err("Refusing real-session runtime or IBus socket; native engine is not approved for system installation".into());
    }
    use std::os::unix::fs::{FileTypeExt, PermissionsExt};
    if session_path != runtime.join("bus")
        || !std::fs::metadata(session_path)
            .map_err(|_| "Session socket unavailable")?
            .file_type()
            .is_socket()
        || !std::fs::metadata(socket)
            .map_err(|_| "IBus socket unavailable")?
            .file_type()
            .is_socket()
        || std::fs::metadata(runtime)
            .map_err(|_| "Runtime unavailable")?
            .permissions()
            .mode()
            & 0o777
            != 0o700
    {
        return Err("Private buses must use mode-0700 runtime and real Unix sockets".into());
    }
    if std::env::var_os("IBUS_USE_PORTAL").is_some() {
        return Err("IBUS_USE_PORTAL must be absent for the private native engine".into());
    }
    Ok(())
}
unsafe extern "C" fn closed(_connection: Handle, _remote: c_int, _error: Handle, data: Handle) {
    unsafe {
        f::g_main_loop_quit(data);
    }
}
pub fn run(experimental: bool) -> Result<(), String> {
    verify_private_environment()?;
    eprintln!(
        "zkey-native: build_source_sha256={}",
        env!("ZKEY_NATIVE_SOURCE_SHA256")
    );
    let config = Config::load(&config::path()?)?;
    if experimental || config.experimental_rewrite {
        eprintln!(
            "zkey-native: EXPERIMENTAL surrounding rewrite; WebKit deletion bug remains a release blocker"
        );
    } else {
        eprintln!("zkey-native: safe native pass-through; unverified rewrites disabled");
    }
    unsafe {
        f::ibus_init();
        let bus = f::ibus_bus_new();
        if bus.is_null() || f::ibus_bus_is_connected(bus) == 0 {
            if !bus.is_null() {
                f::g_object_unref(bus);
            }
            return Err("Cannot connect to private IBus".into());
        }
        let conn = f::ibus_bus_get_connection(bus);
        let mut error = ptr::null_mut();
        let xml = f::cstring(include_str!("engine.xml"))?;
        let node = f::g_dbus_node_info_new_for_xml(xml.as_ptr(), &mut error);
        if node.is_null() {
            f::g_object_unref(bus);
            return Err(f::error_message(error, "IBus schema parse"));
        }
        let mut app = Application {
            conn,
            node,
            registrations: Vec::new(),
            instances: Vec::new(),
            experimental,
            next_id: 0,
            config,
        };
        let pointer = (&mut app as *mut Application).cast();
        let setup = (|| -> Result<(), String> {
            export(
                &mut app,
                c"/org/freedesktop/IBus/Factory",
                FACTORY,
                &FACTORY_VTABLE,
                pointer,
            )?;
            let component = f::ibus_component_new(
                c"org.freedesktop.IBus.ZkeyNative".as_ptr(),
                c"zkey native development".as_ptr(),
                c"0.2.0-dev".as_ptr(),
                c"AGPL-3.0-or-later".as_ptr(),
                c"zkey contributors".as_ptr(),
                c"".as_ptr(),
                c"".as_ptr(),
                c"zkey-native".as_ptr(),
            );
            if component.is_null() {
                return Err("Component allocation failed".into());
            }
            f::g_object_ref_sink(component);
            let desc = f::ibus_engine_desc_new(
                c"zkey-native".as_ptr(),
                c"zkey native".as_ptr(),
                c"Independent native Telex development engine".as_ptr(),
                c"vi".as_ptr(),
                c"AGPL-3.0-or-later".as_ptr(),
                c"zkey contributors".as_ptr(),
                c"input-keyboard".as_ptr(),
                c"us".as_ptr(),
            );
            if desc.is_null() {
                f::g_object_unref(component);
                return Err("Engine description allocation failed".into());
            }
            f::g_object_ref_sink(desc);
            f::ibus_component_add_engine(component, desc);
            f::g_object_unref(desc);
            let ok = f::ibus_bus_register_component(bus, component);
            f::g_object_unref(component);
            if ok == 0 {
                return Err("Private IBus rejected native component".into());
            }
            if let Ok(marker) = std::env::var("ZKEY_NATIVE_READY") {
                let marker = Path::new(&marker);
                let allowed = std::env::var_os("ZKEY_NATIVE_SESSION_ROOT")
                    .map(std::path::PathBuf::from)
                    .unwrap_or_else(|| {
                        Path::new(env!("CARGO_MANIFEST_DIR"))
                            .parent()
                            .expect("manifest has parent")
                            .join(".tmp")
                    })
                    .canonicalize()
                    .map_err(|_| "Scratch unavailable")?;
                let parent = marker
                    .parent()
                    .ok_or("Invalid ready marker")?
                    .canonicalize()
                    .map_err(|_| "Ready marker parent unavailable")?;
                if !parent.starts_with(allowed) {
                    return Err("Ready marker must stay in project scratch".into());
                }
                use std::io::Write;
                use std::os::unix::fs::OpenOptionsExt;
                let mut ready = std::fs::OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .mode(0o600)
                    .open(marker)
                    .map_err(|_| "Cannot create fresh readiness marker")?;
                ready
                    .write_all(b"registered\n")
                    .map_err(|_| "Cannot write readiness marker")?;
            }
            Ok(())
        })();
        let outcome = match setup {
            Err(error) => Err(error),
            Ok(()) => {
                let main_loop = f::g_main_loop_new(ptr::null_mut(), 0);
                let callback: unsafe extern "C" fn() = std::mem::transmute(
                    closed as unsafe extern "C" fn(Handle, c_int, Handle, Handle),
                );
                f::g_signal_connect_data(
                    conn,
                    c"closed".as_ptr(),
                    Some(callback),
                    main_loop,
                    None,
                    0,
                );
                eprintln!("zkey-native: private engine registered; no system input source changed");
                f::g_main_loop_run(main_loop);
                f::g_main_loop_unref(main_loop);
                Err("Private IBus disconnected; native engine stopped".into())
            }
        };
        for id in app.registrations.drain(..).rev() {
            f::g_dbus_connection_unregister_object(conn, id);
        }
        // Touch the owned boxes only after unexporting every callback.
        for instance in &mut app.instances {
            instance.0.state.reset();
        }
        let mut flush_error = ptr::null_mut();
        if f::g_dbus_connection_flush_sync(conn, ptr::null_mut(), &mut flush_error) == 0
            && !flush_error.is_null()
        {
            f::g_error_free(flush_error);
        }
        f::g_dbus_node_info_unref(node);
        f::g_object_unref(bus);
        outcome
    }
}
