// SPDX-License-Identifier: AGPL-3.0-or-later
//! Native preferences as a command line (no GUI toolkit, no system library):
//! `--show` prints the settings, `--set key=value …` validates and saves them
//! through the same audited transaction as before (`config::save`).
use std::io::IsTerminal;
use zkey_native::{
    compose::{HARD_KEY_LIMIT, ToneStyle},
    config::{self, Config, SaveOutcome},
    notify,
};

const KEYS: &str = "enabled, tone_style (modern|traditional), max_word_keys (8..256), experimental_rewrite, webkit_compat";

fn boolean(value: &str) -> Result<bool, String> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err("Expected true or false".into()),
    }
}

/// Apply `key=value` edits on top of `base`. Unknown/duplicate keys and bad values
/// are errors; nothing is returned (so nothing can be saved) unless ALL are valid.
pub fn apply_edits(mut base: Config, edits: &[String]) -> Result<Config, String> {
    let mut seen = Vec::new();
    for edit in edits {
        let (key, value) = edit
            .split_once('=')
            .ok_or("Expected key=value (see --help)")?;
        if seen.contains(&key) {
            return Err(format!("Duplicate setting {key}"));
        }
        seen.push(key);
        match key {
            "enabled" => base.enabled = boolean(value)?,
            "experimental_rewrite" => base.experimental_rewrite = boolean(value)?,
            "webkit_compat" => base.webkit_compat = boolean(value)?,
            "tone_style" => {
                base.style = match value {
                    "modern" => ToneStyle::Modern,
                    "traditional" => ToneStyle::Traditional,
                    _ => return Err("tone_style must be modern or traditional".into()),
                }
            }
            "max_word_keys" => {
                let limit: usize = value
                    .parse()
                    .map_err(|_| "max_word_keys must be a number")?;
                if !(8..=HARD_KEY_LIMIT).contains(&limit) {
                    return Err("max_word_keys must be 8..256".into());
                }
                base.max_word_keys = limit;
            }
            _ => return Err(format!("Unknown setting {key}; valid: {KEYS}")),
        }
    }
    Ok(base)
}

fn describe(config: &Config) -> String {
    config.encode()
}

/// `--show`: print the current settings. A broken file is reported and defaults are
/// shown, but the file is NOT touched; the exit code is 1 so scripts cannot miss it.
pub fn show() -> Result<(), String> {
    let path = config::path()?;
    match Config::load(&path) {
        Ok(config) => {
            println!("# {}\n{}", path.display(), describe(&config));
            Ok(())
        }
        Err(error) => {
            println!(
                "# {}\n# Cấu hình lỗi: {error}. Đang hiện mặc định; chỉ thay khi chạy --set.\n{}",
                path.display(),
                describe(&Config::default())
            );
            Err("Settings file is invalid (not modified)".into())
        }
    }
}

/// `--set key=value …`. On a broken file the defaults are the base (recovery).
pub fn set(edits: &[String]) -> Result<(), String> {
    if edits.is_empty() {
        return Err(format!("Nothing to set; valid keys: {KEYS}"));
    }
    let path = config::path()?;
    let (base, repaired) = match Config::load(&path) {
        Ok(config) => (config, false),
        Err(_) => (Config::default(), true),
    };
    let config = apply_edits(base, edits)?;
    match config::save(&path, &config)? {
        SaveOutcome::Applied => {
            println!(
                "Đã lưu{}. Kiểu dấu áp dụng khi đổi ô nhập; cầu nối WebKit từ lần mở ứng dụng tiếp theo. Không đổi bộ gõ hệ thống.",
                if repaired {
                    " (cấu hình cũ lỗi, đã thay bằng mặc định + giá trị vừa đặt)"
                } else {
                    ""
                }
            );
            Ok(())
        }
        SaveOutcome::AppliedAuditIncomplete => Err(
            "Cấu hình ĐÃ đổi nhưng đồng bộ đĩa/nhật ký chưa đầy đủ. Chưa thể xác nhận lưu bền vững."
                .into(),
        ),
    }
}

/// No argument. At a terminal: show. Launched from a menu (no terminal): tell the
/// user, with a notification, how to change settings — never fail silently.
pub fn default_entry() -> Result<(), String> {
    if std::io::stdout().is_terminal() {
        return show();
    }
    let path = config::path()?;
    let body = match Config::load(&path) {
        Ok(config) => format!(
            "Thiết lập hiện tại:\n{}\nĐể đổi, chạy trong terminal: zkey-native --set tone_style=traditional (khoá: {KEYS}).",
            describe(&config)
        ),
        Err(error) => format!(
            "Cấu hình lỗi: {error}. Chạy trong terminal: zkey-native --set enabled=true để sửa."
        ),
    };
    notify::send("zkey native — Thiết lập", &body, false)
        .map(|_| ())
        .map_err(|e| format!("Cannot show settings: {e}"))
}

/// Visible warning: a critical desktop notification. Err when it could not be delivered.
pub fn alert(message: &str) -> Result<(), String> {
    notify::send("zkey native — Cảnh báo", message, true).map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn edit(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn valid_edits_change_only_the_named_keys() {
        let config = apply_edits(
            Config::default(),
            &edit(&[
                "tone_style=traditional",
                "max_word_keys=64",
                "enabled=false",
            ]),
        )
        .unwrap();
        assert_eq!(config.style, ToneStyle::Traditional);
        assert_eq!(config.max_word_keys, 64);
        assert!(!config.enabled);
        assert_eq!(
            config.experimental_rewrite,
            Config::default().experimental_rewrite
        );
    }

    #[test]
    fn any_invalid_edit_rejects_the_whole_set() {
        for bad in [
            &["tone_style=sloppy"][..],
            &["max_word_keys=7"],
            &["max_word_keys=257"],
            &["max_word_keys=abc"],
            &["enabled=yes"],
            &["unknown=1"],
            &["noequals"],
            &["enabled=true", "enabled=false"],
            &["enabled=true", "tone_style=nope"],
        ] {
            assert!(
                apply_edits(Config::default(), &edit(bad)).is_err(),
                "{bad:?}"
            );
        }
        assert!(apply_edits(Config::default(), &edit(&["max_word_keys=8"])).is_ok());
        assert!(apply_edits(Config::default(), &edit(&["max_word_keys=256"])).is_ok());
    }
}
