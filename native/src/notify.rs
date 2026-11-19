// SPDX-License-Identifier: AGPL-3.0-or-later
//! Desktop notifications (`org.freedesktop.Notifications.Notify`) over our own D-Bus
//! client: the visible warning that replaces the former GTK dialog. A critical
//! notification stays on screen until dismissed (GNOME Shell shows it). Delivery
//! failure is an `Err`, never silent: the caller must report it.
use crate::dbus::{Connection, Value};

const SERVICE: &str = "org.freedesktop.Notifications";
const PATH: &str = "/org/freedesktop/Notifications";

/// Arguments of `Notify(susssasa{sv}i)`: app, replaces_id, icon, summary, body,
/// actions, hints, timeout. `critical` sets urgency=2 and a 0 (never expire) timeout.
pub fn arguments(summary: &str, body: &str, critical: bool) -> Vec<Value> {
    let hints = if critical {
        vec![Value::Dict(
            Box::new(Value::str("urgency")),
            Box::new(Value::Variant(Box::new(Value::Byte(2)))),
        )]
    } else {
        vec![]
    };
    vec![
        Value::str("zkey native"),
        Value::U32(0),
        Value::str(if critical {
            "dialog-warning"
        } else {
            "dialog-information"
        }),
        Value::str(summary),
        Value::str(body),
        Value::Array("s".into(), vec![]),
        Value::Array("{sv}".into(), hints),
        Value::I32(if critical { 0 } else { 8000 }),
    ]
}

fn session_address() -> Result<String, String> {
    if let Ok(address) = std::env::var("DBUS_SESSION_BUS_ADDRESS") {
        return Ok(address);
    }
    let runtime = std::env::var("XDG_RUNTIME_DIR").map_err(|_| "No session bus address")?;
    Ok(format!("unix:path={runtime}/bus"))
}

/// Show a notification; returns its server-side id.
pub fn send(summary: &str, body: &str, critical: bool) -> Result<u32, String> {
    send_to(&session_address()?, summary, body, critical)
}

/// Same, on an explicit bus address (tests use a private bus, never the user's).
pub fn send_to(address: &str, summary: &str, body: &str, critical: bool) -> Result<u32, String> {
    let mut bus = Connection::connect(address)
        .map_err(|_| "Cannot reach the session bus for the notification")?;
    let reply = bus
        .call(
            SERVICE,
            PATH,
            SERVICE,
            "Notify",
            arguments(summary, body, critical),
        )
        .map_err(|_| "No notification service accepted the warning")?;
    reply
        .first()
        .ok_or("Empty Notify reply")?
        .as_u32()
        .map_err(|_| "Malformed Notify reply".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn arguments_match_the_notify_signature() {
        let args = arguments("zkey", "hỏng", true);
        let signature: String = args.iter().map(Value::signature).collect();
        assert_eq!(signature, "susssasa{sv}i");
        assert_eq!(args[3], Value::str("zkey"));
        assert_eq!(args[4], Value::str("hỏng"));
        assert_eq!(args[7], Value::I32(0), "critical never expires");
        let Value::Array(_, hints) = &args[6] else {
            panic!("hints")
        };
        assert_eq!(hints.len(), 1, "critical carries urgency=2");
    }

    #[test]
    fn plain_notification_has_no_urgency_hint_and_expires() {
        let args = arguments("a", "b", false);
        let Value::Array(_, hints) = &args[6] else {
            panic!("hints")
        };
        assert!(hints.is_empty());
        assert_eq!(args[7], Value::I32(8000));
    }
}
