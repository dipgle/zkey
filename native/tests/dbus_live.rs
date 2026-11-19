// SPDX-License-Identifier: AGPL-3.0-or-later
//! Oracle test: our std-only D-Bus code against the system's real `dbus-daemon`
//! and `gdbus`. Both are used ONLY here, as an independent reference; the shipped
//! binary links neither. A private bus under project scratch, never the user's.
//! Exit-state rule: if the reference tools are missing the test FAILS (cannot
//! measure is not green).
use std::{
    io::{BufRead, BufReader},
    path::PathBuf,
    process::{Child, Command, Stdio},
    thread,
};
use zkey_native::dbus::{Connection, METHOD_CALL, Value};

struct Bus {
    child: Child,
    dir: PathBuf,
    address: String,
}
impl Bus {
    fn start(tag: &str) -> Bus {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join(".tmp")
            .join(format!("dbus-live-{tag}-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let socket = dir.join("bus");
        let address = format!("unix:path={}", socket.display());
        let mut child = Command::new("dbus-daemon")
            .args(["--session", "--nofork", "--print-address=1"])
            .arg(format!("--address={address}"))
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("dbus-daemon must exist: the oracle cannot be measured without it");
        let mut line = String::new();
        BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut line)
            .unwrap();
        assert!(line.starts_with("unix:path="), "daemon printed no address");
        Bus {
            child,
            dir,
            address,
        }
    }
}
impl Drop for Bus {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = std::fs::remove_dir_all(&self.dir);
    }
}

#[test]
fn our_client_speaks_to_the_real_daemon() {
    let bus = Bus::start("client");
    let mut c = Connection::connect(&bus.address).unwrap();
    assert!(
        c.unique_name.starts_with(':'),
        "Hello gave {:?}",
        c.unique_name
    );
    c.request_name("org.zkey.Test").unwrap();
    // A second owner must be refused (DO_NOT_QUEUE) — the reply code is read, not assumed.
    let mut other = Connection::connect(&bus.address).unwrap();
    assert!(other.request_name("org.zkey.Test").is_err());
    let names = c
        .call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ListNames",
            vec![],
        )
        .unwrap();
    let Value::Array(element, items) = &names[0] else {
        panic!("ListNames is not an array")
    };
    assert_eq!(element, "s");
    assert!(items.contains(&Value::str("org.zkey.Test")));
    // Owner lookup returns exactly our unique name (daemon-side truth).
    let owner = c
        .call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "GetNameOwner",
            vec![Value::str("org.zkey.Test")],
        )
        .unwrap();
    assert_eq!(owner[0].as_str().unwrap(), c.unique_name);
    // The daemon's own error path: unknown name => error reply, not a hang.
    let missing = c.call(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "GetNameOwner",
        vec![Value::str("org.zkey.Nobody")],
    );
    assert!(missing.unwrap_err().contains("NameHasNoOwner"));
}

#[test]
fn the_real_gdbus_client_gets_correct_replies_from_our_server() {
    let bus = Bus::start("server");
    let mut server = Connection::connect(&bus.address).unwrap();
    server.request_name("org.zkey.Echo").unwrap();
    let handle = thread::spawn(move || {
        // Serve until the Stop call.
        loop {
            let m = server.next_message().unwrap();
            if m.kind != METHOD_CALL {
                continue;
            }
            match m.member.as_deref() {
                Some("Echo") => {
                    // Mixed alignment on purpose: string, uint32, bool, array of dict, variant.
                    let text = m.body[0].as_str().unwrap().to_owned();
                    server
                        .reply(
                            &m,
                            vec![
                                Value::Str(text.to_uppercase()),
                                Value::U32(m.body[1].as_u32().unwrap() + 1),
                                Value::Bool(true),
                                Value::Array(
                                    "{sv}".into(),
                                    vec![Value::Dict(
                                        Box::new(Value::str("k")),
                                        Box::new(Value::Variant(Box::new(Value::I32(-3)))),
                                    )],
                                ),
                                Value::Variant(Box::new(Value::Struct(vec![
                                    Value::Byte(9),
                                    Value::str("é"),
                                ]))),
                            ],
                        )
                        .unwrap();
                }
                Some("Fail") => server
                    .reply_error(&m, "org.zkey.Error.Boom", "nope")
                    .unwrap(),
                Some("Stop") => {
                    server.reply(&m, vec![]).unwrap();
                    return;
                }
                _ => server
                    .reply_error(&m, "org.freedesktop.DBus.Error.UnknownMethod", "unknown")
                    .unwrap(),
            }
        }
    });
    let gdbus = |member: &str, args: &[&str]| {
        let output = Command::new("gdbus")
            .args([
                "call",
                "--address",
                &bus.address,
                "--dest",
                "org.zkey.Echo",
                "--object-path",
                "/org/zkey/Echo",
                "--method",
            ])
            .arg(format!("org.zkey.Echo.{member}"))
            .args(args)
            .output()
            .expect("gdbus must exist: the oracle cannot be measured without it");
        (
            output.status.success(),
            String::from_utf8_lossy(&output.stdout).into_owned(),
            String::from_utf8_lossy(&output.stderr).into_owned(),
        )
    };
    let (ok, out, err) = gdbus("Echo", &["tiếng", "uint32 41"]);
    assert!(ok, "gdbus failed: {err}");
    // gdbus' own rendering of what it decoded from OUR bytes (an a{sv} prints as a dict).
    assert_eq!(
        out.trim(),
        "('TIẾNG', uint32 42, true, {'k': <-3>}, <(byte 0x09, 'é')>)"
    );
    let (ok, _, err) = gdbus("Fail", &[]);
    assert!(
        !ok && err.contains("org.zkey.Error.Boom") && err.contains("nope"),
        "error path: {err}"
    );
    let (ok, _, err) = gdbus("Missing", &[]);
    assert!(
        !ok && err.contains("UnknownMethod"),
        "unknown method: {err}"
    );
    let (ok, _, err) = gdbus("Stop", &[]);
    assert!(ok, "stop: {err}");
    handle.join().unwrap();
}

#[test]
fn signals_we_emit_reach_a_real_subscriber() {
    let bus = Bus::start("signal");
    let mut emitter = Connection::connect(&bus.address).unwrap();
    let mut monitor = Command::new("dbus-monitor")
        .args([
            "--address",
            &bus.address,
            "type='signal',interface='org.zkey.Sig'",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("dbus-monitor must exist: the oracle cannot be measured without it");
    let mut lines = BufReader::new(monitor.stdout.take().unwrap()).lines();
    // dbus-monitor prints once subscribed; wait for its NameAcquired line before emitting.
    loop {
        let line = lines.next().expect("monitor closed early").unwrap();
        if line.contains("NameAcquired") || line.contains("org.freedesktop.DBus") {
            break;
        }
    }
    thread::sleep(std::time::Duration::from_millis(300));
    emitter
        .emit(
            "/org/zkey/Sig",
            "org.zkey.Sig",
            "Committed",
            vec![Value::str("hoà"), Value::U32(7)],
        )
        .unwrap();
    let mut seen = String::new();
    for _ in 0..12 {
        let line = lines
            .next()
            .expect("monitor closed before the signal")
            .unwrap();
        seen.push_str(&line);
        seen.push('\n');
        if seen.contains("uint32 7") {
            break;
        }
    }
    let _ = monitor.kill();
    let _ = monitor.wait();
    assert!(
        seen.contains("member=Committed"),
        "signal header not seen:\n{seen}"
    );
    assert!(
        seen.contains("string \"hoà\""),
        "signal body not seen:\n{seen}"
    );
    assert!(
        seen.contains("uint32 7"),
        "second argument not seen:\n{seen}"
    );
}

#[test]
fn notification_reaches_a_service_and_dbus_monitor_decodes_every_argument() {
    use zkey_native::notify;
    let bus = Bus::start("notify");
    let mut service = Connection::connect(&bus.address).unwrap();
    service
        .request_name("org.freedesktop.Notifications")
        .unwrap();
    let mut monitor = Command::new("dbus-monitor")
        .args([
            "--address",
            &bus.address,
            "type='method_call',member='Notify'",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("dbus-monitor must exist: the oracle cannot be measured without it");
    let mut lines = BufReader::new(monitor.stdout.take().unwrap()).lines();
    loop {
        let line = lines.next().expect("monitor closed early").unwrap();
        if line.contains("NameAcquired") || line.contains("org.freedesktop.DBus") {
            break;
        }
    }
    thread::sleep(std::time::Duration::from_millis(300));
    let server = thread::spawn(move || {
        loop {
            let m = service.next_message().unwrap();
            if m.kind == METHOD_CALL && m.member.as_deref() == Some("Notify") {
                service.reply(&m, vec![Value::U32(77)]).unwrap();
                return;
            }
        }
    });
    // The client under test talks to this private bus, never the user's.
    let id = notify::send_to(&bus.address, "Tiêu đề", "Telex đã tắt", true).unwrap();
    assert_eq!(id, 77, "reply id is read back from the service");
    server.join().unwrap();
    let mut seen = String::new();
    for _ in 0..40 {
        let line = lines
            .next()
            .expect("monitor closed before the call")
            .unwrap();
        seen.push_str(&line);
        seen.push('\n');
        if line.trim() == "int32 0" {
            break;
        }
    }
    let _ = monitor.kill();
    let _ = monitor.wait();
    for expected in [
        "member=Notify",
        "string \"zkey native\"",
        "string \"Tiêu đề\"",
        "string \"Telex đã tắt\"",
        "string \"dialog-warning\"",
        "string \"urgency\"",
        "byte 2",
        "int32 0",
    ] {
        assert!(seen.contains(expected), "missing {expected:?} in:\n{seen}");
    }
}

#[test]
fn notification_failure_is_an_error_not_silence() {
    use zkey_native::notify;
    let bus = Bus::start("nonotify");
    // A bus with no notification service: the call must fail loudly.
    assert!(notify::send_to(&bus.address, "x", "y", true).is_err());
}
