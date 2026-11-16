// SPDX-License-Identifier: AGPL-3.0-or-later
//! A deliberately small, strict TOML schema, not a permissive TOML parser.
//! Only the scalar forms we emit are accepted; unknown/duplicate keys fail.
use crate::compose::{HARD_KEY_LIMIT, ToneStyle};
use std::{
    collections::BTreeSet,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::unix::fs::OpenOptionsExt,
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Config {
    pub enabled: bool,
    pub style: ToneStyle,
    pub max_word_keys: usize,
    pub experimental_rewrite: bool,
    pub webkit_compat: bool,
    pub generation: String,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            enabled: true,
            style: ToneStyle::Modern,
            max_word_keys: HARD_KEY_LIMIT,
            experimental_rewrite: false,
            webkit_compat: false,
            generation: "initial".into(),
        }
    }
}
fn boolean(value: &str) -> Result<bool, String> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err("Expected TOML boolean".into()),
    }
}
impl Config {
    pub fn parse(text: &str) -> Result<Self, String> {
        let mut config = Self::default();
        let mut seen = BTreeSet::new();
        for line in text.lines() {
            let line = line.split('#').next().unwrap_or("").trim();
            if line.is_empty() {
                continue;
            }
            let (key, value) = line
                .split_once('=')
                .ok_or("Expected key = value in native settings")?;
            let (key, value) = (key.trim(), value.trim());
            if !seen.insert(key) {
                return Err("Duplicate native setting".into());
            }
            match key {
                "schema" if value == "1" => {}
                "schema" => return Err("Unsupported native settings schema".into()),
                "enabled" => config.enabled = boolean(value)?,
                "experimental_rewrite" => config.experimental_rewrite = boolean(value)?,
                "webkit_compat" => config.webkit_compat = boolean(value)?,
                "tone_style" => {
                    config.style = match value {
                        "\"modern\"" => ToneStyle::Modern,
                        "\"traditional\"" => ToneStyle::Traditional,
                        _ => return Err("Invalid tone style".into()),
                    }
                }
                "max_word_keys" => {
                    config.max_word_keys = value.parse().map_err(|_| "Invalid word key limit")?;
                    if !(8..=HARD_KEY_LIMIT).contains(&config.max_word_keys) {
                        return Err("Word key limit must be 8..256".into());
                    }
                }
                "generation" => {
                    let token = value
                        .strip_prefix('"')
                        .and_then(|v| v.strip_suffix('"'))
                        .ok_or("Invalid generation token")?;
                    if token.is_empty()
                        || token.len() > 64
                        || !token.bytes().all(|b| b.is_ascii_alphanumeric())
                    {
                        return Err("Invalid generation token".into());
                    }
                    config.generation = token.into();
                }
                _ => return Err("Unknown native setting".into()),
            }
        }
        if !seen.contains("schema") {
            return Err("Native settings must declare schema = 1".into());
        }
        Ok(config)
    }
    pub fn encode(&self) -> String {
        format!(
            "schema = 1\nenabled = {}\ntone_style = \"{}\"\nmax_word_keys = {}\nexperimental_rewrite = {}\nwebkit_compat = {}\ngeneration = \"{}\"\n",
            self.enabled,
            if self.style == ToneStyle::Modern {
                "modern"
            } else {
                "traditional"
            },
            self.max_word_keys,
            self.experimental_rewrite,
            self.webkit_compat,
            self.generation
        )
    }
    pub fn load(path: &Path) -> Result<Self, String> {
        match fs::read_to_string(path) {
            Ok(text) => {
                let config = Self::parse(&text)?;
                if config.generation != "initial" {
                    let audit = path
                        .parent()
                        .ok_or("Settings path needs a parent")?
                        .join("changes.log");
                    let journal = fs::read_to_string(audit)
                        .map_err(|_| "Settings exist but their audit journal is unavailable")?;
                    let commit = format!("commit {}", config.generation);
                    if !journal.lines().any(|line| line == commit) {
                        return Err("Settings transaction has no durable audit commit; repair in native settings".into());
                    }
                }
                Ok(config)
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Self::default()),
            Err(_) => Err("Cannot read native settings".into()),
        }
    }
}
pub fn path() -> Result<PathBuf, String> {
    if let Some(path) = std::env::var_os("ZKEY_NATIVE_CONFIG_PATH") {
        return Ok(PathBuf::from(path));
    }
    let base = match std::env::var_os("XDG_CONFIG_HOME") {
        Some(value) => PathBuf::from(value),
        None => {
            PathBuf::from(std::env::var_os("HOME").ok_or("HOME is unavailable")?).join(".config")
        }
    };
    Ok(base.join("zkey-native/config.toml"))
}
pub fn token() -> Result<String, String> {
    let mut bytes = [0u8; 16];
    File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut bytes))
        .map_err(|_| "Cannot obtain system randomness")?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}
#[derive(Debug, PartialEq, Eq)]
pub enum SaveOutcome {
    Applied,
    AppliedAuditIncomplete,
}
pub fn save(path: &Path, config: &Config) -> Result<SaveOutcome, String> {
    // Validate even values constructed programmatically, not only parsed data.
    Config::parse(&config.encode())?;
    let directory = path
        .parent()
        .ok_or("Settings path needs a parent directory")?;
    fs::create_dir_all(directory).map_err(|_| "Cannot create native settings directory")?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .mode(0o600)
        .open(directory.join("config.lock"))
        .map_err(|_| "Cannot open settings lock")?;
    lock.try_lock()
        .map_err(|_| "Another process is saving native settings")?;
    let id = token()?;
    let mut new = config.clone();
    new.generation = id.clone();
    let mut journal = OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .open(directory.join("changes.log"))
        .map_err(|_| "Cannot open settings audit journal; nothing saved")?;
    let actor = std::env::var("USER")
        .ok()
        .filter(|v| {
            v.bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        })
        .unwrap_or_else(|| "local-owner".into());
    let epoch = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| "System clock predates epoch")?
        .as_millis();
    writeln!(journal,"intent {id} epoch_ms={epoch} actor={actor} enabled={} tone={:?} max_keys={} experimental={} webkit_compat={}",new.enabled,new.style,new.max_word_keys,new.experimental_rewrite,new.webkit_compat)
        .and_then(|_|journal.sync_all()).map_err(|_|"Cannot persist settings audit intent; nothing saved")?;
    let temporary = directory.join(format!(".config-{id}.tmp"));
    let outcome = (|| -> Result<(), String> {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&temporary)
            .map_err(|_| "Cannot stage native settings")?;
        file.write_all(new.encode().as_bytes())
            .and_then(|_| file.sync_all())
            .map_err(|_| "Cannot persist staged native settings")?;
        fs::rename(&temporary, path).map_err(|_| "Cannot atomically replace native settings")?;
        Ok(())
    })();
    if let Err(error) = outcome {
        if temporary.exists() && fs::remove_file(&temporary).is_err() {
            eprintln!("zkey-native: failed settings staging file retained");
        }
        return Err(error);
    }
    // After rename the config IS visible. Never report 'not saved' if a later
    // durability/audit operation fails; the UI must expose partial success.
    if File::open(directory).and_then(|d| d.sync_all()).is_err()
        || writeln!(journal, "commit {id}")
            .and_then(|_| journal.sync_all())
            .is_err()
    {
        return Ok(SaveOutcome::AppliedAuditIncomplete);
    }
    Ok(SaveOutcome::Applied)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Scratch(PathBuf);
    impl Scratch {
        fn new() -> Self {
            let p = Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../.tmp")
                .join(format!("native-config-{}", token().unwrap()));
            fs::create_dir_all(&p).unwrap();
            Self(p)
        }
    }
    impl Drop for Scratch {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
    #[test]
    fn exact_round_trip_and_safe_defaults() {
        let c = Config::default();
        assert_eq!(Config::parse(&c.encode()).unwrap(), c);
        assert!(!c.experimental_rewrite);
        assert!(!c.webkit_compat);
    }
    #[test]
    fn webkit_compatibility_requires_explicit_opt_in_and_is_audited() {
        assert!(
            !Config::parse("schema=1\nenabled=true\n")
                .unwrap()
                .webkit_compat
        );
        assert!(Config::parse("schema=1\nwebkit_compat=1").is_err());
        let scratch = Scratch::new();
        let path = scratch.0.join("config.toml");
        let config = Config {
            webkit_compat: true,
            ..Config::default()
        };
        assert_eq!(save(&path, &config).unwrap(), SaveOutcome::Applied);
        assert!(Config::load(&path).unwrap().webkit_compat);
        assert!(
            fs::read_to_string(scratch.0.join("changes.log"))
                .unwrap()
                .contains("webkit_compat=true")
        );
    }
    #[test]
    fn malformed_unknown_duplicate_and_unversioned_are_rejected() {
        for text in [
            "enabled = true",
            "schema=2",
            "schema=1\nunknown=true",
            "schema=1\nenabled=1",
            "schema=1\nenabled=true\nenabled=false",
            "schema=1\nmax_word_keys=257",
            "schema=1\ngeneration=\"a\\n\"",
        ] {
            assert!(Config::parse(text).is_err(), "{text}");
        }
    }
    #[test]
    fn missing_config_is_not_the_same_as_broken_config() {
        let s = Scratch::new();
        let p = s.0.join("config.toml");
        assert_eq!(Config::load(&p).unwrap(), Config::default());
        fs::write(&p, "broken").unwrap();
        assert!(Config::load(&p).is_err());
    }
    #[test]
    fn saving_persists_only_settings_and_audits_the_generation() {
        let s = Scratch::new();
        let p = s.0.join("config.toml");
        let c = Config {
            style: ToneStyle::Traditional,
            ..Config::default()
        };
        assert_eq!(save(&p, &c).unwrap(), SaveOutcome::Applied);
        let restored = Config::load(&p).unwrap();
        assert_eq!(restored.style, ToneStyle::Traditional);
        assert_ne!(restored.generation, "initial");
        let journal = fs::read_to_string(s.0.join("changes.log")).unwrap();
        assert!(journal.contains(&format!("intent {} ", restored.generation)));
        assert!(journal.contains(&format!("commit {}", restored.generation)));
        assert!(!journal.contains("typed"));
    }
    #[test]
    fn concurrent_save_is_refused_without_touching_configuration() {
        let s = Scratch::new();
        let p = s.0.join("config.toml");
        let lock = File::create(s.0.join("config.lock")).unwrap();
        lock.lock().unwrap();
        assert!(save(&p, &Config::default()).is_err());
        assert!(!p.exists());
    }
    #[test]
    fn blocked_audit_prevents_configuration_mutation() {
        let s = Scratch::new();
        let p = s.0.join("config.toml");
        fs::create_dir(s.0.join("changes.log")).unwrap();
        assert!(save(&p, &Config::default()).is_err());
        assert!(!p.exists());
    }
    #[test]
    fn interrupted_post_rename_audit_is_not_silently_accepted_on_restart() {
        let s = Scratch::new();
        let p = s.0.join("config.toml");
        let c = Config {
            generation: "uncommitted123".into(),
            ..Config::default()
        };
        fs::write(&p, c.encode()).unwrap();
        fs::write(s.0.join("changes.log"), "intent uncommitted123\n").unwrap();
        assert!(Config::load(&p).is_err());
        fs::write(
            s.0.join("changes.log"),
            "intent uncommitted123\ncommit uncommitted123\n",
        )
        .unwrap();
        assert_eq!(Config::load(&p).unwrap(), c);
    }
}
