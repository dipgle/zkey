// SPDX-License-Identifier: AGPL-3.0-or-later
//! Private application launcher. Product path is native Rust + system daemons.
//! It never edits input sources, environment.d, .bashrc or desktop IBus.
use std::{
    fs::{self, OpenOptions},
    os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};
use zkey_native::{
    config,
    dbus::{Connection, Value},
    ibus,
};

struct Process(Child);
impl Drop for Process {
    fn drop(&mut self) {
        match self.0.try_wait() {
            Ok(Some(_)) => {}
            _ => {
                if self.0.kill().and_then(|_| self.0.wait()).is_err() {
                    eprintln!("zkey-native: failed to reap an owned child process");
                }
            }
        }
    }
}
struct Scratch {
    path: PathBuf,
    keep: bool,
}
impl Drop for Scratch {
    fn drop(&mut self) {
        if self.keep {
            eprintln!(
                "zkey-native: private session retained for diagnostics: {}",
                self.path.display()
            );
        }
        // Successful cleanup is performed synchronously by run(), so a cleanup
        // error changes the exit status rather than becoming a green warning.
    }
}
fn wait_file(path: &Path, process: &mut Process, deadline: Instant) -> Result<(), String> {
    while !path.exists() {
        if process
            .0
            .try_wait()
            .map_err(|_| "Cannot inspect owned service")?
            .is_some()
        {
            return Err("Private service exited before readiness".into());
        }
        if Instant::now() > deadline {
            return Err("Private service readiness timed out".into());
        }
        thread::sleep(Duration::from_millis(10));
    }
    Ok(())
}
fn log(path: &Path) -> Result<Stdio, String> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .open(path)
        .map(Stdio::from)
        .map_err(|_| "Cannot open private service log".into())
}
pub fn run(arguments: &[String], experimental: bool, webkit: bool) -> Result<(), String> {
    let executable = std::env::current_exe().map_err(|_| "Cannot locate native executable")?;
    let base = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    if !base.is_dir() {
        return Err("Runtime base directory is unavailable".into());
    }
    // Linux sockaddr_un has a fixed 108-byte path budget; AT-SPI appends its
    // own socket name beneath runtime. A long branding prefix + 128-bit hex
    // broke the actual accessibility bridge on project-local acceptance.
    // This name is not an authentication token (ownership/mode provide that).
    let root = base.join(format!("zn-{}", &config::token()?[..16]));
    fs::DirBuilder::new()
        .mode(0o700)
        .create(&root)
        .map_err(|_| "Cannot create private native session")?;
    let mut scratch = Scratch {
        path: root.clone(),
        keep: true,
    };
    for name in ["runtime", "config", "cache", "data"] {
        fs::DirBuilder::new()
            .mode(0o700)
            .create(root.join(name))
            .map_err(|_| "Cannot create private application state")?;
    }
    let root = root
        .canonicalize()
        .map_err(|_| "Cannot resolve private native session")?;
    let socket = root.join("runtime/bus");
    let address = format!("unix:path={}", socket.display());
    let preference = config::path()?;
    let preference = if preference.is_absolute() {
        preference
    } else {
        std::env::current_dir()
            .map_err(|_| "Cannot resolve settings path")?
            .join(preference)
    };
    let webkit = webkit || config::Config::load(&preference)?.webkit_compat;
    if webkit {
        use std::io::Write;
        let bridge = include_bytes!(concat!(env!("OUT_DIR"), "/libzkey_webkit_bridge.so"));
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o700)
            .open(root.join("libzkey_webkit_bridge.so"))
            .map_err(|_| "Cannot stage the private WebKit bridge")?;
        file.write_all(bridge)
            .and_then(|_| file.sync_all())
            .map_err(|_| "Cannot persist the private WebKit bridge")?;
        eprintln!(
            "zkey-native: explicit process-local WebKit compatibility enabled; system libraries unchanged"
        );
    }
    // Every activated service inherits the private runtime from the BUS itself.
    let mut daemon = Command::new("dbus-daemon");
    daemon
        .args(["--session", "--nofork", "--nopidfile"])
        .arg(format!("--address={address}"))
        .env("XDG_RUNTIME_DIR", root.join("runtime"))
        .env("XDG_CONFIG_HOME", root.join("config"))
        .env("XDG_CACHE_HOME", root.join("cache"))
        .env("XDG_DATA_HOME", root.join("data"))
        .env("GSETTINGS_BACKEND", "memory")
        .env("GIO_USE_VFS", "local")
        .env_remove("DBUS_SESSION_BUS_ADDRESS")
        .env_remove("WAYLAND_DISPLAY")
        .stdout(log(&root.join("bus.log"))?)
        .stderr(log(&root.join("bus.log"))?);
    let mut daemon = Process(
        daemon
            .spawn()
            .map_err(|_| "Cannot start system dbus-daemon")?,
    );
    wait_file(
        &socket,
        &mut daemon,
        Instant::now() + Duration::from_secs(8),
    )?;
    let mut child = Command::new(executable);
    child
        .arg("--inside-run")
        .arg(if experimental { "experimental" } else { "safe" })
        .args(arguments)
        .env("DBUS_SESSION_BUS_ADDRESS", address)
        .env("XDG_RUNTIME_DIR", root.join("runtime"))
        .env("XDG_CONFIG_HOME", root.join("config"))
        .env("XDG_CACHE_HOME", root.join("cache"))
        .env("XDG_DATA_HOME", root.join("data"))
        .env("GSETTINGS_BACKEND", "memory")
        .env("GIO_USE_VFS", "local")
        .env("NO_AT_BRIDGE", "1")
        .env(
            "IBUS_ADDRESS",
            format!("unix:path={}", root.join("ibus.sock").display()),
        )
        .env("IBUS_ADDRESS_FILE", root.join("ibus-address"))
        .env("ZKEY_NATIVE_SESSION_ROOT", &root)
        .env("ZKEY_NATIVE_CONFIG_PATH", preference)
        .env("ZKEY_NATIVE_WEBKIT_COMPAT", if webkit { "1" } else { "0" })
        .env_remove("IBUS_USE_PORTAL");
    // The BUS services need isolated state, but application recovery documents
    // must not be put in a temporary data tree that is deleted on close.
    let home = PathBuf::from(std::env::var_os("HOME").ok_or("HOME is unavailable")?);
    for (key, suffix) in [
        ("XDG_CONFIG_HOME", ".config"),
        ("XDG_CACHE_HOME", ".cache"),
        ("XDG_DATA_HOME", ".local/share"),
    ] {
        child.env(
            format!("ZKEY_NATIVE_APP_{key}"),
            std::env::var_os(key)
                .map(PathBuf::from)
                .unwrap_or_else(|| home.join(suffix)),
        );
    }
    if let Some(value) = std::env::var_os("NO_AT_BRIDGE") {
        child.env("ZKEY_NATIVE_APP_NO_AT_BRIDGE", value);
    } else {
        child.env_remove("ZKEY_NATIVE_APP_NO_AT_BRIDGE");
    }
    // Relative Wayland sockets are tied to the REAL runtime, not our private one.
    if let Some(wayland) = std::env::var_os("WAYLAND_DISPLAY") {
        let display = Path::new(&wayland);
        child.env(
            "WAYLAND_DISPLAY",
            if display.is_absolute() {
                display.to_path_buf()
            } else {
                base.join(display)
            },
        );
    }
    let status = child
        .status()
        .map_err(|_| "Cannot start native application supervisor")?;
    // Reap the bus before deleting its services' runtime/mount directories.
    drop(daemon);
    if status.success() {
        // The bus has exited, but an activated document portal may need a short
        // interval to release its PRIVATE FUSE mount. Never unmount the desktop
        // or recurse through a still-mounted tree and call cleanup successful.
        let deadline = Instant::now() + Duration::from_secs(4);
        loop {
            let mounts = fs::read_to_string("/proc/self/mountinfo")
                .map_err(|_| "Cannot verify private runtime mount cleanup")?;
            let needle = root.to_string_lossy();
            if !mounts.lines().any(|line| {
                line.split_whitespace()
                    .nth(4)
                    .is_some_and(|mount| mount.starts_with(needle.as_ref()))
            }) {
                break;
            }
            if Instant::now() >= deadline {
                return Err(
                    "Private service mount still alive; session retained, no forced unmount".into(),
                );
            }
            thread::sleep(Duration::from_millis(20));
        }
        fs::remove_dir_all(&scratch.path)
            .map_err(|_| "Private session cleanup incomplete; diagnostics retained")?;
        scratch.keep = false;
        Ok(())
    } else {
        Err("Private native application session failed; diagnostics retained".into())
    }
}
fn activation() -> Result<(), String> {
    let items: Vec<_> = [
        "IBUS_ADDRESS",
        "IBUS_ADDRESS_FILE",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "GSETTINGS_BACKEND",
        "GIO_USE_VFS",
        "NO_AT_BRIDGE",
    ]
    .iter()
    .filter_map(|key| {
        std::env::var(key)
            .ok()
            .map(|value| (key.to_string(), value))
    })
    .collect();
    if items.is_empty() {
        return Err("Activation dictionary cannot be empty".into());
    }
    let dictionary = Value::Array(
        "{ss}".into(),
        items
            .iter()
            .map(|(key, value)| Value::Dict(Box::new(Value::str(key)), Box::new(Value::str(value))))
            .collect(),
    );
    let session =
        std::env::var("DBUS_SESSION_BUS_ADDRESS").map_err(|_| "Private session bus unavailable")?;
    let mut bus =
        Connection::connect(&session).map_err(|_| "Private session bus connection failed")?;
    bus.call(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "UpdateActivationEnvironment",
        vec![dictionary],
    )
    .map(|_| ())
    .map_err(|_| "Private activation environment failed".into())
}
/// Select the native engine on the PRIVATE daemon (never the desktop's).
fn select_engine() -> Result<(), String> {
    let address = std::env::var("IBUS_ADDRESS").map_err(|_| "Missing private IBus address")?;
    let mut bus = Connection::connect(&address)
        .map_err(|_| "Cannot create private IBus control connection")?;
    bus.call(
        ibus::BUS_NAME,
        ibus::BUS_PATH,
        ibus::BUS_NAME,
        "SetGlobalEngine",
        vec![Value::str("zkey-native")],
    )
    .map(|_| ())
    .map_err(|_| "Cannot select native engine on the private daemon".into())
}
pub fn inside(arguments: &[String], experimental: bool) -> Result<(), String> {
    let root = PathBuf::from(
        std::env::var_os("ZKEY_NATIVE_SESSION_ROOT").ok_or("Missing native session root")?,
    )
    .canonicalize()
    .map_err(|_| "Session root unavailable")?;
    let runtime = std::env::var("XDG_RUNTIME_DIR").map_err(|_| "Private runtime unavailable")?;
    let session =
        std::env::var("DBUS_SESSION_BUS_ADDRESS").map_err(|_| "Private session bus unavailable")?;
    let ibus = std::env::var("IBUS_ADDRESS").map_err(|_| "Private IBus address unavailable")?;
    verify_layout(&root, &runtime, &session, &ibus)?;
    activation()?;
    let address = std::env::var("IBUS_ADDRESS").map_err(|_| "Missing private IBus address")?;
    let mut daemon = Command::new("ibus-daemon");
    daemon
        .args([
            "--single",
            "--panel=disable",
            "--config=disable",
            "--emoji-extension=disable",
            "--cache=none",
        ])
        .arg(format!("--address={address}"))
        .stdout(log(&root.join("ibus.log"))?)
        .stderr(log(&root.join("ibus.log"))?);
    let mut daemon = Process(
        daemon
            .spawn()
            .map_err(|_| "Cannot start private IBus daemon")?,
    );
    let deadline = Instant::now() + Duration::from_secs(10);
    wait_file(&root.join("ibus.sock"), &mut daemon, deadline)?;
    let executable = std::env::current_exe().map_err(|_| "Cannot locate native executable")?;
    let mut engine = Command::new(&executable);
    engine.arg("--engine");
    if experimental {
        engine.arg("--experimental-rewrite");
    }
    engine
        .env("ZKEY_NATIVE_READY", root.join("ready"))
        .stdout(log(&root.join("engine.log"))?)
        .stderr(log(&root.join("engine.log"))?);
    let mut engine = Process(engine.spawn().map_err(|_| "Cannot start native engine")?);
    wait_file(&root.join("ready"), &mut engine, deadline)?;
    select_engine()?;
    let default = vec![
        "gnome-text-editor".to_string(),
        "--standalone".to_string(),
        "--new-window".to_string(),
    ];
    let arguments = if arguments.is_empty() {
        &default
    } else {
        arguments
    };
    let mut application_command = Command::new(&arguments[0]);
    application_command.args(&arguments[1..]);
    for key in ["XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"] {
        if let Some(original) = std::env::var_os(format!("ZKEY_NATIVE_APP_{key}")) {
            application_command.env(key, original);
        }
    }
    if let Some(original) = std::env::var_os("ZKEY_NATIVE_APP_NO_AT_BRIDGE") {
        application_command.env("NO_AT_BRIDGE", original);
    } else {
        application_command.env_remove("NO_AT_BRIDGE");
    }
    if std::env::var("ZKEY_NATIVE_WEBKIT_COMPAT").as_deref() == Ok("1") {
        let bridge = root.join("libzkey_webkit_bridge.so");
        if !bridge.is_file() {
            return Err("Opted-in private WebKit bridge is unavailable".into());
        }
        let mut preload = bridge.into_os_string();
        if let Some(previous) = std::env::var_os("LD_PRELOAD").filter(|value| !value.is_empty()) {
            preload.push(":");
            preload.push(previous);
        }
        application_command.env("LD_PRELOAD", preload);
    }
    let mut application = Process(
        application_command
            .env("GTK_IM_MODULE", "ibus")
            .env("QT_IM_MODULE", "ibus")
            .env("XMODIFIERS", "@im=ibus")
            .env("IBUS_ENABLE_SYNC_MODE", "1")
            .spawn()
            .map_err(|_| "Cannot start requested application")?,
    );
    let mut failed = false;
    let mut settings_reported = false;
    let mut alert: Option<Process> = None;
    loop {
        let invalid_settings = root
            .join("settings-invalid")
            .try_exists()
            .map_err(|_| "Cannot inspect input settings health")?;
        if let Some(result) = session_exit(
            &mut application,
            &mut engine,
            &mut daemon,
            failed || invalid_settings,
        )? {
            return result;
        }
        if !failed
            && (engine
                .0
                .try_wait()
                .map_err(|_| "Cannot inspect native engine")?
                .is_some()
                || daemon
                    .0
                    .try_wait()
                    .map_err(|_| "Cannot inspect private IBus")?
                    .is_some())
        {
            failed = true;
            eprintln!(
                "zkey-native: input service stopped; save the document, Telex is unavailable"
            );
            let message = "zkey native đã dừng. Hãy lưu tài liệu; Telex không còn hoạt động. Không tự khởi động lại hoặc gõ lại chữ.";
            match Command::new(&executable).args(["--alert", message]).spawn() {
                Ok(child) => alert = Some(Process(child)),
                Err(_) => eprintln!("zkey-native: cannot show failure notification"),
            }
        }
        if invalid_settings && !settings_reported {
            settings_reported = true;
            eprintln!(
                "zkey-native: settings rejected; visible warning opened, composition bypassed"
            );
            let message = "Cấu hình zkey native không hợp lệ. Telex đã tắt để giữ nguyên phím. Hãy mở Thiết lập và lưu cấu hình hợp lệ; không cần đóng tài liệu.";
            match Command::new(&executable).args(["--alert", message]).spawn() {
                Ok(child) => alert = Some(Process(child)),
                Err(_) => return Err("Cannot show native settings failure warning".into()),
            }
        } else if !invalid_settings {
            settings_reported = false;
        }
        if let Some(dialog) = &mut alert
            && let Some(status) = dialog
                .0
                .try_wait()
                .map_err(|_| "Cannot inspect failure notification")?
        {
            if !status.success() {
                // Delivery failed: say so (the keys stay literal either way).
                eprintln!(
                    "zkey-native: warning notification was not delivered; see its error above"
                );
            }
            alert = None;
        }
        thread::sleep(Duration::from_millis(50));
    }
}

fn session_exit(
    application: &mut Process,
    engine: &mut Process,
    daemon: &mut Process,
    failed: bool,
) -> Result<Option<Result<(), String>>, String> {
    // Centralize the terminal-state decision so the close/crash race can be
    // exercised deterministically with real owned child processes.
    if let Some(status) = application
        .0
        .try_wait()
        .map_err(|_| "Cannot inspect launched application")?
    {
        // Check service liveness AFTER observing app exit, before declaring a
        // clean session. Both may have ended within the same polling interval.
        let service_failed = engine
            .0
            .try_wait()
            .map_err(|_| "Cannot inspect native engine")?
            .is_some()
            || daemon
                .0
                .try_wait()
                .map_err(|_| "Cannot inspect private IBus")?
                .is_some();
        return Ok(Some(if status.success() && !failed && !service_failed {
            Ok(())
        } else {
            Err("Application or native input service failed".into())
        }));
    }
    Ok(None)
}

fn verify_layout(root: &Path, runtime: &str, session: &str, ibus: &str) -> Result<(), String> {
    use std::os::unix::fs::{FileTypeExt, MetadataExt};
    let name = root
        .file_name()
        .and_then(|name| name.to_str())
        .and_then(|name| name.strip_prefix("zn-"))
        .ok_or("Not a native private session directory")?;
    if name.len() != 16 || !name.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("Invalid private session identifier".into());
    }
    let metadata = fs::metadata(root).map_err(|_| "Session root unavailable")?;
    let owner = fs::metadata("/proc/self")
        .map_err(|_| "Cannot verify session owner")?
        .uid();
    if metadata.uid() != owner || metadata.permissions().mode() & 0o777 != 0o700 {
        return Err("Native session root must be owned by this user and mode 0700".into());
    }
    if Path::new(runtime)
        .canonicalize()
        .map_err(|_| "Runtime unavailable")?
        != root.join("runtime")
        || session.split(',').next()
            != Some(format!("unix:path={}", root.join("runtime/bus").display()).as_str())
        || ibus != format!("unix:path={}", root.join("ibus.sock").display())
    {
        return Err("Refusing mismatched or real-session bus addresses".into());
    }
    if !fs::metadata(root.join("runtime/bus"))
        .map_err(|_| "Private session socket unavailable")?
        .file_type()
        .is_socket()
    {
        return Err("Private session bus is not a Unix socket".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn input_service_exit_cannot_hide_behind_successful_app_exit() {
        let exited = || {
            let mut p = Process(Command::new("/usr/bin/true").spawn().unwrap());
            p.0.wait().unwrap();
            p
        };
        let mut app = exited();
        let mut engine = exited();
        let mut daemon = Process(Command::new("/usr/bin/sleep").arg("10").spawn().unwrap());
        assert!(
            session_exit(&mut app, &mut engine, &mut daemon, false)
                .unwrap()
                .unwrap()
                .is_err()
        );
        let mut app = exited();
        let mut live = Process(Command::new("/usr/bin/sleep").arg("10").spawn().unwrap());
        assert!(
            session_exit(&mut app, &mut live, &mut daemon, false)
                .unwrap()
                .unwrap()
                .is_ok()
        );
    }
    #[test]
    fn private_supervisor_never_accepts_a_real_or_mismatched_bus() {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../.tmp");
        fs::create_dir_all(&base).unwrap();
        let root = base
            .canonicalize()
            .unwrap()
            .join(format!("zn-{}", &config::token().unwrap()[..16]));
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        fs::DirBuilder::new()
            .mode(0o700)
            .create(root.join("runtime"))
            .unwrap();
        let socket = std::os::unix::net::UnixListener::bind(root.join("runtime/bus")).unwrap();
        let runtime = root.join("runtime").to_string_lossy().into_owned();
        let bus = format!("unix:path={runtime}/bus");
        let ibus = format!("unix:path={}/ibus.sock", root.display());
        assert!(verify_layout(&root, &runtime, &bus, &ibus).is_ok());
        assert!(verify_layout(&root, &runtime, "unix:path=/run/user/1000/bus", &ibus).is_err());
        assert!(verify_layout(&root, &runtime, &bus, "unix:path=/run/user/1000/ibus").is_err());
        fs::set_permissions(&root, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(verify_layout(&root, &runtime, &bus, &ibus).is_err());
        drop(socket);
        fs::remove_dir_all(root).unwrap();
    }
}
