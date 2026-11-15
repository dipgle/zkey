// SPDX-License-Identifier: AGPL-3.0-or-later
//! Persistent Telex service for the shell line editor (shell/zkey.bash).
//!
//! One request per line: 'm' (modern tone) or 'c' (classic) then the word's
//! keys/text. Reply "=<word>" or "!" for invalid input. A composed result that
//! is not a plausible Vietnamese syllable is replied unchanged, so English and
//! command words stay as typed. Never logs input.
use std::io::{self, BufRead, Write};
use zkey_core::telex::{MAX_KEYS, compose, is_vietnamese, valid_syllable};

fn reply(request: &str) -> Option<String> {
    let mut chars = request.chars();
    let modern = match chars.next()? {
        'm' => true,
        'c' => false,
        _ => return None,
    };
    let word = chars.as_str();
    if word.chars().count() > MAX_KEYS || !word.chars().all(|c| c.is_ascii_alphabetic() || is_vietnamese(c)) {
        return None;
    }
    let composed = compose(word, modern);
    Some(if composed == word || valid_syllable(&composed) { composed } else { word.to_string() })
}

fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let mut out = io::stdout().lock();
    for line in stdin.lock().lines() {
        match reply(&line?) {
            Some(word) => writeln!(out, "={word}")?,
            None => writeln!(out, "!")?,
        }
        out.flush()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::reply;

    #[test]
    fn protocol() {
        assert_eq!(reply("mtieengs").as_deref(), Some("tiếng"));
        assert_eq!(reply("mtiêngs").as_deref(), Some("tiếng"));
        assert_eq!(reply("choas").as_deref(), Some("hóa"));
        assert_eq!(reply("mstatus").as_deref(), Some("status"));
        assert_eq!(reply("madd").as_deref(), Some("add"));
        assert_eq!(reply("mclass").as_deref(), Some("class"));
        assert_eq!(reply("m").as_deref(), Some(""));
        for bad in ["", "xab", "ma-b", "m🙂"] {
            assert_eq!(reply(bad), None, "{bad}");
        }
    }
}
