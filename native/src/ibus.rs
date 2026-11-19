// SPDX-License-Identifier: AGPL-3.0-or-later
//! IBus wire contract on top of `dbus`: how IBus serialises Text / Component /
//! EngineDesc. Type strings were taken from libibus 1.5.34 itself (python GI
//! `IBus.Serializable.serialize_object(..).get_type_string()`), used only as a
//! reference while writing this file; nothing here calls libibus.
use crate::dbus::Value;

pub const BUS_NAME: &str = "org.freedesktop.IBus";
pub const BUS_PATH: &str = "/org/freedesktop/IBus";
pub const FACTORY_PATH: &str = "/org/freedesktop/IBus/Factory";
pub const FACTORY: &str = "org.freedesktop.IBus.Factory";
pub const ENGINE: &str = "org.freedesktop.IBus.Engine";
pub const SERVICE: &str = "org.freedesktop.IBus.Service";

/// Component (well-known bus) name the production engine owns; matches `<name>` in its component XML.
pub const COMPONENT_NAME: &str = "org.freedesktop.IBus.ZkeyNative";

/// Address of the LIVE ibus-daemon: `IBUS_ADDRESS` if set, else the newest file in
/// `<dir>` (normally `~/.config/ibus/bus`) whose `IBUS_DAEMON_PID` is alive. The
/// file name depends on machine id + display, so scan instead of guessing it.
pub fn address_from_dir(dir: &std::path::Path) -> Option<String> {
    let mut files: Vec<_> = std::fs::read_dir(dir)
        .ok()?
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let modified = entry.metadata().ok()?.modified().ok()?;
            Some((modified, entry.path()))
        })
        .collect();
    files.sort_by_key(|entry| std::cmp::Reverse(entry.0));
    for (_, path) in files {
        let Ok(text) = std::fs::read_to_string(&path) else {
            continue;
        };
        let value = |key: &str| {
            text.lines()
                .filter(|line| !line.starts_with('#'))
                .find_map(|line| line.strip_prefix(key)?.strip_prefix('='))
        };
        let alive = value("IBUS_DAEMON_PID")
            .and_then(|pid| pid.parse::<u32>().ok())
            .is_some_and(|pid| std::path::Path::new(&format!("/proc/{pid}")).exists());
        if let (true, Some(address)) = (alive, value("IBUS_ADDRESS")) {
            return Some(address.to_owned());
        }
    }
    None
}

pub fn daemon_address() -> Result<String, String> {
    if let Ok(address) = std::env::var("IBUS_ADDRESS") {
        return Ok(address);
    }
    let home = std::env::var_os("HOME").ok_or("HOME is unavailable")?;
    let config = std::env::var_os("XDG_CONFIG_HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| std::path::Path::new(&home).join(".config"));
    address_from_dir(&config.join("ibus/bus"))
        .ok_or_else(|| "No running ibus-daemon address found".into())
}

fn empty_attachments() -> Value {
    Value::Array("{sv}".into(), vec![])
}

/// `v` holding `(sa{sv}sv)` = ("IBusText", {}, text, <("IBusAttrList", {}, [])>)
pub fn text(value: &str) -> Value {
    Value::Variant(Box::new(Value::Struct(vec![
        Value::str("IBusText"),
        empty_attachments(),
        Value::str(value),
        Value::Variant(Box::new(Value::Struct(vec![
            Value::str("IBusAttrList"),
            empty_attachments(),
            Value::Array("v".into(), vec![]),
        ]))),
    ])))
}

/// Read only the documented Text tuple. An unexpected shape is an error; no
/// client-supplied type name is ever instantiated, and attributes are ignored.
pub fn text_of(value: &Value) -> Result<String, String> {
    let wrapped = value
        .as_variant()
        .map_err(|_| "Expected IBus.Text variant")?;
    if wrapped.signature() != "(sa{sv}sv)" {
        return Err("Surrounding argument is not a valid IBus.Text tuple".into());
    }
    let parts = wrapped.as_struct()?;
    if parts[0].as_str()? != "IBusText" {
        return Err("Surrounding argument is not a valid IBus.Text tuple".into());
    }
    Ok(parts[2].as_str()?.to_owned())
}

/// `(sa{sv}ssssssssussssssss)`: eight strings, rank, then eight optional strings
/// (hotkeys, symbol, setup, layout variant/option, version, textdomain, icon prop key), all empty here.
pub fn engine_desc(fields: [&str; 8]) -> Value {
    // fields: name, longname, description, language, license, author, icon, layout
    let mut parts = vec![Value::str("IBusEngineDesc"), empty_attachments()];
    parts.extend(fields.map(Value::str));
    parts.push(Value::U32(0));
    parts.extend((0..8).map(|_| Value::str("")));
    Value::Struct(parts)
}

/// `(sa{sv}ssssssssavav)`: name, description, version, license, author, homepage,
/// command line, text domain, observed paths (none), engines.
pub fn component(fields: [&str; 8], engines: Vec<Value>) -> Value {
    let mut parts = vec![Value::str("IBusComponent"), empty_attachments()];
    parts.extend(fields.map(Value::str));
    parts.push(Value::Array("v".into(), vec![]));
    parts.push(Value::Array(
        "v".into(),
        engines
            .into_iter()
            .map(|e| Value::Variant(Box::new(e)))
            .collect(),
    ));
    Value::Struct(parts)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signatures_equal_what_libibus_serialises() {
        assert_eq!(text("x").as_variant().unwrap().signature(), "(sa{sv}sv)");
        let desc = engine_desc(["n", "l", "d", "vi", "L", "a", "i", "us"]);
        assert_eq!(desc.signature(), "(sa{sv}ssssssssussssssss)");
        let comp = component(["n", "d", "v", "L", "a", "", "", "t"], vec![desc]);
        assert_eq!(comp.signature(), "(sa{sv}ssssssssavav)");
    }

    #[test]
    fn text_roundtrips_and_rejects_foreign_shapes() {
        assert_eq!(text_of(&text("tiếng 🙂")).unwrap(), "tiếng 🙂");
        assert_eq!(text_of(&text("")).unwrap(), "");
        assert!(text_of(&Value::U32(1)).is_err());
        assert!(text_of(&Value::Variant(Box::new(Value::str("not an IBus object")))).is_err());
        // Right shape, wrong type name: refused rather than trusted.
        let foreign = Value::Variant(Box::new(Value::Struct(vec![
            Value::str("IBusSomethingElse"),
            empty_attachments(),
            Value::str("x"),
            Value::Variant(Box::new(Value::U32(0))),
        ])));
        assert!(text_of(&foreign).is_err());
    }

    #[test]
    fn daemon_address_comes_from_the_newest_live_daemon_file() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join(".tmp")
            .join(format!("ibus-addr-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let me = std::process::id();
        let write = |name: &str, pid: u32, address: &str| {
            std::fs::write(
                root.join(name),
                format!("# comment IBUS_ADDRESS=ignored\nIBUS_ADDRESS={address}\nIBUS_DAEMON_PID={pid}\n"),
            )
            .unwrap();
        };
        // A dead daemon's file (stale) must NOT be returned, even when it is newer.
        write("live", me, "unix:path=/live");
        std::thread::sleep(std::time::Duration::from_millis(20));
        write("stale", 4_000_000, "unix:path=/stale");
        assert_eq!(address_from_dir(&root).as_deref(), Some("unix:path=/live"));
        std::fs::remove_file(root.join("live")).unwrap();
        assert_eq!(
            address_from_dir(&root),
            None,
            "only a dead daemon left => not measurable"
        );
        assert_eq!(address_from_dir(&root.join("missing")), None);
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn text_survives_the_wire_encoding() {
        let mut bytes = Vec::new();
        crate::dbus::marshal(&text("hoà"), &mut bytes).unwrap();
        let back = crate::dbus::unmarshal("v", &bytes).unwrap();
        assert_eq!(text_of(&back[0]).unwrap(), "hoà");
    }
}
