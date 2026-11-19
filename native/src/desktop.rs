// SPDX-License-Identifier: AGPL-3.0-or-later
//! IBus engine service over our own D-Bus implementation (`zkey_native::dbus`):
//! no GLib, GObject, GIO or libibus.
use std::{collections::HashMap, path::Path};
use zkey_native::{
    config::{self, Config},
    dbus::{Connection, METHOD_CALL, Message, Value},
    ibus,
    session::{Edit, Session},
};

const PROPERTIES: &str = "org.freedesktop.DBus.Properties";
const INTROSPECTABLE: &str = "org.freedesktop.DBus.Introspectable";
const PEER: &str = "org.freedesktop.DBus.Peer";
const INTROSPECTION: &str = include_str!("engine.xml");
const MAX_CONTEXTS: usize = 256;

struct Instance {
    state: Session,
    requested: bool,
    ctrl: bool,
    retired: bool,
    trace: bool,
    experimental: bool,
    latest_type: Option<(u32, u32)>,
}
struct Application {
    conn: Connection,
    instances: HashMap<String, Instance>,
    experimental: bool,
    next_id: u64,
    config: Config,
}
/// A reply the caller sees as a D-Bus error. Never carries keys or typed text.
struct Reject {
    name: &'static str,
    text: &'static str,
}
const FAILED: Reject = Reject {
    name: "org.freedesktop.DBus.Error.Failed",
    text: "zkey-native desktop operation failed (input omitted)",
};
const UNKNOWN_OBJECT: Reject = Reject {
    name: "org.freedesktop.DBus.Error.UnknownObject",
    text: "unknown object",
};
const UNKNOWN_METHOD: Reject = Reject {
    name: "org.freedesktop.DBus.Error.UnknownMethod",
    text: "unknown method",
};
fn failed(detail: String) -> Reject {
    // Detail strings are fixed messages of this program (decoder/gate names), never
    // key values or typed text; they are shown ONLY when the user turned tracing on.
    if std::env::var_os("ZKEY_NATIVE_TRACE").is_some() {
        eprintln!("zkey-native: request failed because: {detail}");
    }
    FAILED
}

fn emit(conn: &mut Connection, path: &str, name: &str, values: Vec<Value>) -> Result<(), String> {
    conn.emit(path, ibus::ENGINE, name, values)
}
fn apply(conn: &mut Connection, path: &str, edit: Edit) -> Result<bool, String> {
    if (edit.remove > 0 || !edit.insert.is_empty())
        && std::env::var_os("ZKEY_NATIVE_TRACE").is_some()
    {
        // Counts only (how many chars deleted/inserted), never the text itself.
        eprintln!(
            "zkey-native: edit sent remove={} insert_chars={}",
            edit.remove,
            edit.insert.chars().count()
        );
    }
    if edit.remove > 0 {
        emit(
            conn,
            path,
            "DeleteSurroundingText",
            vec![Value::I32(-(edit.remove as i32)), Value::U32(edit.remove)],
        )?;
    }
    if !edit.insert.is_empty() {
        emit(conn, path, "CommitText", vec![ibus::text(&edit.insert)])?;
    }
    Ok(edit.handled)
}
fn clear_preedit(conn: &mut Connection, path: &str) -> Result<(), String> {
    emit(
        conn,
        path,
        "UpdatePreeditText",
        vec![
            ibus::text(""),
            Value::U32(0),
            Value::Bool(false),
            Value::U32(0),
        ],
    )
}
fn key(
    conn: &mut Connection,
    path: &str,
    instance: &mut Instance,
    value: u32,
    state: u32,
) -> Result<bool, String> {
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
        emit(conn, path, "RequireSurroundingText", vec![])?;
        instance.requested = true;
    }
    if value == 0xff08 {
        instance.state.backspace();
        return Ok(false);
    }
    if value == 0xff1b {
        let edit = instance.state.escape();
        return apply(conn, path, edit);
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
        apply(conn, path, edit)
    } else {
        instance.state.reset();
        Ok(false)
    }
}

fn create_engine(app: &mut Application, params: &[Value]) -> Result<Vec<Value>, String> {
    if params.first().ok_or("Malformed D-Bus tuple")?.as_str()? != "zkey-native" {
        return Err("Unknown engine".into());
    }
    // Destroyed contexts are reclaimed at the next factory request, outside
    // their own callback. Do not retain words or leak one entry per focus.
    app.instances.retain(|_, instance| !instance.retired);
    // Explicit bound, reported as a failure, never silently evict a context.
    if app.instances.len() >= MAX_CONTEXTS {
        return Err("Native context bound reached; restart private test session".into());
    }
    app.next_id = app
        .next_id
        .checked_add(1)
        .ok_or("Engine identifier space exhausted")?;
    let path = format!("/org/freedesktop/IBus/Engine/Native{}", app.next_id);
    app.instances.insert(
        path.clone(),
        Instance {
            state: Session::new(
                app.config.style,
                app.config.enabled,
                app.config.max_word_keys,
                app.experimental || app.config.experimental_rewrite,
            ),
            requested: false,
            ctrl: false,
            retired: false,
            trace: std::env::var_os("ZKEY_NATIVE_TRACE").is_some(),
            experimental: app.experimental,
            latest_type: None,
        },
    );
    eprintln!("zkey-native: context registered");
    Ok(vec![Value::Path(path)])
}

fn engine_method(
    conn: &mut Connection,
    path: &str,
    instance: &mut Instance,
    method: &str,
    params: &[Value],
) -> Result<Vec<Value>, String> {
    let arg = |index: usize| params.get(index).ok_or("Malformed D-Bus tuple");
    if instance.retired {
        return Err("Engine context already destroyed".into());
    }
    match method {
        "ProcessKeyEvent" => {
            let handled = key(conn, path, instance, arg(0)?.as_u32()?, arg(2)?.as_u32()?)?;
            if instance.trace {
                eprintln!(
                    "zkey-native: key-event handled={handled} protected={}",
                    instance.state.protected()
                );
            }
            Ok(vec![Value::Bool(handled)])
        }
        "SetCapabilities" => {
            let caps = arg(0)?.as_u32()?;
            if instance.trace {
                // Bit 5 (value 32) = client supports surrounding text; without it the
                // engine passes keys through. A number only, never text.
                eprintln!(
                    "zkey-native: capabilities caps={caps} surrounding={}",
                    caps & (1 << 5) != 0
                );
            }
            instance.state.capabilities(caps);
            Ok(vec![])
        }
        "SetSurroundingText" => {
            if instance.trace {
                eprintln!(
                    "zkey-native: surrounding-event protected={}",
                    instance.state.protected()
                );
            }
            if !instance.state.protected() {
                let text = ibus::text_of(arg(0)?)?;
                if text.len() > 1_048_576 {
                    instance.state.reset();
                    return Err("Surrounding payload exceeds safety bound".into());
                }
                let edit = instance.state.snapshot(
                    &text,
                    arg(1)?.as_u32()? as usize,
                    arg(2)?.as_u32()? as usize,
                );
                apply(conn, path, edit)?;
            }
            Ok(vec![])
        }
        "FocusIn" | "FocusInId" | "FocusOut" | "FocusOutId" | "Reset" | "Disable" | "Enable"
        | "Destroy" => {
            if matches!(method, "FocusIn" | "FocusInId") {
                match config::path().and_then(|path| Config::load(&path)) {
                    Ok(config) => {
                        instance.state.configure(&config, instance.experimental);
                        settings_status(false)?;
                    }
                    Err(_) => {
                        // A corrupt/incomplete settings transaction must not
                        // silently keep an older 'enabled' decision alive.
                        instance.state.enabled = false;
                        instance.state.reset();
                        eprintln!(
                            "zkey-native: settings invalid; composition bypassed until valid settings are restored"
                        );
                        settings_status(true)?;
                    }
                }
            }
            if method == "Reset" {
                instance.state.client_reset();
            } else {
                instance.state.reset();
            }
            instance.ctrl = false;
            instance.requested = false;
            if matches!(method, "FocusIn" | "FocusInId") {
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
            if matches!(method, "FocusOut" | "FocusOutId" | "Disable" | "Destroy") {
                instance.state.leave_context();
            }
            if instance.trace {
                eprintln!(
                    "zkey-native: context-state event={method} protected={}",
                    instance.state.protected()
                );
            }
            if method == "Destroy" {
                instance.retired = true;
            }
            clear_preedit(conn, path)?;
            Ok(vec![])
        }
        // Methods of the IBus Engine interface that a Telex engine has nothing to do for.
        // Answering them with an error made every new context log "composition not
        // certified" (measured 18/11: PanelExtensionRegisterKeys on each focus).
        "SetCursorLocation"
        | "PropertyActivate"
        | "PropertyShow"
        | "PropertyHide"
        | "PageUp"
        | "PageDown"
        | "CursorUp"
        | "CursorDown"
        | "CandidateClicked"
        | "ProcessHandWritingEvent"
        | "CancelHandWriting"
        | "PanelExtensionReceived"
        | "PanelExtensionRegisterKeys" => Ok(vec![]),
        // The method name is a protocol constant from ibus-daemon (shown only when tracing).
        _ => Err(format!("Unsupported native engine method {method}")),
    }
}

fn properties(
    instance: &mut Instance,
    conn: &mut Connection,
    path: &str,
    member: &str,
    params: &[Value],
) -> Result<Vec<Value>, String> {
    let arg = |index: usize| params.get(index).ok_or("Malformed D-Bus tuple");
    // ActiveSurroundingText=true makes IBus request surrounding eagerly on
    // focus, even from VTE which has no retrieve-surrounding implementation.
    // Ask explicitly in key() only after capability + content gates pass.
    let readable = |name: &str| match name {
        "FocusId" => Some(true),
        "ActiveSurroundingText" => Some(false),
        _ => None,
    };
    match member {
        "Get" => {
            let value = readable(arg(1)?.as_str()?).ok_or("Unknown property")?;
            Ok(vec![Value::Variant(Box::new(Value::Bool(value)))])
        }
        "GetAll" => {
            let entries = if arg(0)?.as_str()? == ibus::ENGINE {
                ["FocusId", "ActiveSurroundingText"]
                    .iter()
                    .map(|name| {
                        Value::Dict(
                            Box::new(Value::str(name)),
                            Box::new(Value::Variant(Box::new(Value::Bool(
                                readable(name) == Some(true),
                            )))),
                        )
                    })
                    .collect()
            } else {
                vec![]
            };
            Ok(vec![Value::Array("{sv}".into(), entries)])
        }
        "Set" => {
            if arg(1)?.as_str()? != "ContentType" {
                return Err("Unknown property".into());
            }
            let pair = arg(2)?.as_variant()?.as_struct()?;
            let purpose = pair.first().ok_or("Malformed ContentType")?.as_u32()?;
            let hints = pair.get(1).ok_or("Malformed ContentType")?.as_u32()?;
            instance.state.content(purpose, hints);
            instance.latest_type = Some((purpose, hints));
            if instance.trace {
                eprintln!(
                    "zkey-native: content-type purpose={purpose} protected={}",
                    instance.state.protected()
                );
            }
            if instance.state.protected() {
                clear_preedit(conn, path)?;
            }
            Ok(vec![])
        }
        _ => Err("Unsupported property method".into()),
    }
}

fn handle(app: &mut Application, message: &Message) -> Result<Vec<Value>, Reject> {
    let path = message.path.as_deref().unwrap_or("");
    let interface = message.interface.as_deref().unwrap_or("");
    let member = message.member.as_deref().unwrap_or("");
    match (interface, member) {
        (PEER, "Ping") => return Ok(vec![]),
        (INTROSPECTABLE, "Introspect") => return Ok(vec![Value::str(INTROSPECTION)]),
        _ => {}
    }
    if path == ibus::FACTORY_PATH {
        return if interface == ibus::FACTORY && member == "CreateEngine" {
            create_engine(app, &message.body).map_err(failed)
        } else {
            Err(UNKNOWN_METHOD)
        };
    }
    let Application {
        conn, instances, ..
    } = app;
    let instance = instances.get_mut(path).ok_or(UNKNOWN_OBJECT)?;
    if instance.trace && member != "ProcessKeyEvent" {
        // Which calls a client's input path makes, in order (protocol names only).
        eprintln!("zkey-native: call {member}");
    }
    match interface {
        PROPERTIES => properties(instance, conn, path, member, &message.body).map_err(failed),
        ibus::ENGINE | ibus::SERVICE => {
            engine_method(conn, path, instance, member, &message.body).map_err(failed)
        }
        _ => Err(UNKNOWN_METHOD),
    }
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

fn ready_marker() -> Result<(), String> {
    let Ok(marker) = std::env::var("ZKEY_NATIVE_READY") else {
        return Ok(());
    };
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
        .map_err(|_| "Cannot write readiness marker".into())
}

/// `system = false`: private test engine (registers its own component, refuses the
/// real session). `system = true` (`--ibus`): started BY the user's ibus-daemon from
/// the installed component XML; owns the component name and serves the factory.
pub fn run(experimental: bool, system: bool) -> Result<(), String> {
    if !system {
        verify_private_environment()?;
    }
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
    let address = if system {
        ibus::daemon_address()?
    } else {
        std::env::var("IBUS_ADDRESS").map_err(|_| "Missing private IBus address")?
    };
    let conn = Connection::connect(&address).map_err(|_| "Cannot connect to IBus")?;
    let mut app = Application {
        conn,
        instances: HashMap::new(),
        experimental,
        next_id: 0,
        config,
    };
    if system {
        // The daemon found us through the component XML; it creates the factory
        // proxy when this name appears on the bus.
        app.conn
            .request_name(ibus::COMPONENT_NAME)
            .map_err(|_| "IBus component name is already owned")?;
        eprintln!(
            "zkey-native: system IBus engine serving; input source set by the user, not by this process"
        );
        return serve(app);
    }
    let component = ibus::component(
        [
            "org.freedesktop.IBus.ZkeyNative",
            "zkey native development",
            "0.2.0-dev",
            "AGPL-3.0-or-later",
            "zkey contributors",
            "",
            "",
            "zkey-native",
        ],
        vec![ibus::engine_desc([
            "zkey-native",
            "zkey native",
            "Independent native Telex development engine",
            "vi",
            "AGPL-3.0-or-later",
            "zkey contributors",
            "input-keyboard",
            "us",
        ])],
    );
    app.conn
        .call(
            ibus::BUS_NAME,
            ibus::BUS_PATH,
            ibus::BUS_NAME,
            "RegisterComponent",
            vec![Value::Variant(Box::new(component))],
        )
        .map_err(|_| "Private IBus rejected native component")?;
    ready_marker()?;
    eprintln!("zkey-native: private engine registered; no system input source changed");
    serve(app)
}

fn serve(mut app: Application) -> Result<(), String> {
    let outcome = loop {
        let message = match app.conn.next_message() {
            Ok(message) => message,
            Err(_) => break Err("Private IBus disconnected; native engine stopped".to_owned()),
        };
        if message.kind != METHOD_CALL {
            continue; // signals (NameOwnerChanged …) and stray replies carry no request
        }
        let sent = match handle(&mut app, &message) {
            Ok(body) => app.conn.reply(&message, body),
            Err(reject) => {
                if reject.name == FAILED.name {
                    // Do not include D-Bus arguments, key values or typed text.
                    eprintln!("zkey-native: desktop request failed; composition not certified");
                }
                app.conn.reply_error(&message, reject.name, reject.text)
            }
        };
        if sent.is_err() {
            break Err("Private IBus disconnected; native engine stopped".to_owned());
        }
    };
    // Touch the sessions only after the loop: drop retained words.
    for instance in app.instances.values_mut() {
        instance.state.reset();
    }
    outcome
}
