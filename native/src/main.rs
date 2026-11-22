// SPDX-License-Identifier: AGPL-3.0-or-later
use std::io::{self, BufRead, Write};
use zkey_native::compose::{Composer, HARD_KEY_LIMIT, ToneStyle, valid_syllable};
mod desktop;
mod launch;
mod settings;

fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args_os()
        .skip(1)
        .map(|arg| {
            arg.into_string()
                .map_err(|_| "Non-UTF-8 command argument is unsupported (contents omitted)")
        })
        .collect::<Result<_, _>>()?;
    match args.as_slice() {
        [flag] if flag == "--build-info" => {
            println!(
                "{{\"version\":\"{}\",\"source_sha256\":\"{}\",\"status\":\"development-not-release\"}}",
                env!("CARGO_PKG_VERSION"),
                env!("ZKEY_NATIVE_SOURCE_SHA256")
            );
            Ok(())
        }
        [] => settings::default_entry(),
        [flag] if flag == "--version" => {
            println!(
                "zkey-native {} (development; not system-certified)",
                env!("CARGO_PKG_VERSION")
            );
            Ok(())
        }
        [flag] if matches!(flag.as_str(), "--help" | "-h") => {
            println!(
                "zkey-native — independent Rust development build\n\n--show                     Print the settings (also --settings, and the default at a terminal)\n--set KEY=VALUE ...        Validate and save settings (enabled, tone_style, max_word_keys, experimental_rewrite, webkit_compat)\n--ibus [--experimental-rewrite]\n                           IBus engine started by the user's ibus-daemon (install with scripts/native-ime.py)\n--run [APPLICATION ARGS]   Private application session; system IME unchanged\n--experimental-rewrite --run APPLICATION ARGS\n                           Explicit unverified surrounding rewrite\n--webkit-compat --experimental-rewrite --run APPLICATION ARGS\n                           Opt-in process-local GTK3/WebKit bridge\n--compose WORD             Print one Telex result\n--line [traditional]       Bounded UTF-8 word-per-line protocol (default tone style: modern)\n--version                  Build version\n\nNot approved for system installation; compatibility is scoped to launched applications."
            );
            Ok(())
        }
        [flag, rest @ ..] if flag == "--run" => launch::run(rest, false, false),
        [flag, run, rest @ ..] if flag == "--experimental-rewrite" && run == "--run" => {
            launch::run(rest, true, false)
        }
        [flag, run, rest @ ..] if flag == "--webkit-compat" && run == "--run" => {
            launch::run(rest, false, true)
        }
        [flag, experimental, run, rest @ ..]
            if flag == "--webkit-compat"
                && experimental == "--experimental-rewrite"
                && run == "--run" =>
        {
            launch::run(rest, true, true)
        }
        [flag, mode, rest @ ..]
            if flag == "--inside-run" && matches!(mode.as_str(), "safe" | "experimental") =>
        {
            launch::inside(rest, mode == "experimental")
        }
        [flag] if matches!(flag.as_str(), "--settings" | "--show") => settings::show(),
        [flag, edits @ ..] if flag == "--set" => settings::set(edits),
        [flag, message] if flag == "--alert" => settings::alert(message),
        [flag] if flag == "--engine" => desktop::run(false, false),
        [flag, experimental] if flag == "--engine" && experimental == "--experimental-rewrite" => {
            desktop::run(true, false)
        }
        // Started by the user's ibus-daemon from the installed component XML.
        [flag] if flag == "--ibus" => desktop::run(false, true),
        [flag, experimental] if flag == "--ibus" && experimental == "--experimental-rewrite" => {
            desktop::run(true, true)
        }
        [flag, text] if flag == "--compose" => {
            let mut composer = Composer::new(ToneStyle::Modern);
            for key in text.chars() {
                composer.push(key).map_err(|e| e.to_string())?;
            }
            println!("{}", composer.text());
            Ok(())
        }
        [flag] if flag == "--line" => {
            line_protocol(io::stdin().lock(), ToneStyle::Modern, io::stdout().lock())
        }
        [flag, style] if flag == "--line" && style == "traditional" => line_protocol(
            io::stdin().lock(),
            ToneStyle::Traditional,
            io::stdout().lock(),
        ),
        _ => Err("Unknown command; use zkey-native --help".into()),
    }
}

fn line_protocol(
    mut input: impl BufRead,
    style: ToneStyle,
    mut output: impl Write,
) -> Result<(), String> {
    let mut pending = Vec::new();
    let mut overflow = false;
    loop {
        let block = input.fill_buf().map_err(|_| "Cannot read line protocol")?;
        if block.is_empty() {
            if !pending.is_empty() || overflow {
                line_reply(&pending, overflow, style, &mut output)?;
            }
            break;
        }
        let newline = block.iter().position(|b| *b == b'\n');
        let used = newline.unwrap_or(block.len());
        if !overflow {
            if used > (HARD_KEY_LIMIT * 4).saturating_sub(pending.len()) {
                overflow = true;
                pending.clear();
            } else {
                pending.extend_from_slice(&block[..used]);
            }
        }
        input.consume(used + usize::from(newline.is_some()));
        if newline.is_some() {
            line_reply(&pending, overflow, style, &mut output)?;
            pending.clear();
            overflow = false;
        }
    }
    Ok(())
}
fn line_reply(
    bytes: &[u8],
    overflow: bool,
    style: ToneStyle,
    out: &mut impl Write,
) -> Result<(), String> {
    // This is an explicit data protocol, never a diagnostic/input log.
    let mut composer = Composer::new(style);
    let bytes = bytes.strip_suffix(b"\r").unwrap_or(bytes);
    let raw = std::str::from_utf8(bytes).ok();
    let valid =
        !overflow && raw.is_some_and(|line| line.chars().all(|key| composer.push(key).is_ok()));
    let reply = match raw {
        // A result that is not a plausible Vietnamese syllable keeps the keys
        // exactly as typed, so command words stay commands.
        Some(line) if valid => {
            let composed = composer.text();
            if composed == line || valid_syllable(&composed) {
                composed
            } else {
                line.to_string()
            }
        }
        _ => "!".into(),
    };
    writeln!(out, "{reply}")
        .and_then(|_| out.flush())
        .map_err(|_| "Cannot write line protocol".into())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("zkey-native: {error}");
        let first = std::env::args_os().nth(1);
        // Only a launch from a menu/launcher needs a visible warning; command-line
        // verbs (--show, --set, --compose …) report on stderr and by exit code.
        let graphical = first.as_ref().is_some_and(|flag| {
            matches!(
                flag.to_str(),
                Some("--run" | "--experimental-rewrite" | "--webkit-compat")
            )
        });
        if graphical {
            if std::env::var_os("ZKEY_TEST_DISPLAY").is_some() {
                // Private acceptance observes the error/exit code and must not post a
                // notification to whatever desktop the test happens to run beside.
                eprintln!(
                    "zkey-native: private test display; fatal notification skipped, failure exit retained"
                );
            } else if let Err(_dialog_error) = settings::alert(&format!(
                "Không khởi động được zkey native: {error}. Bộ gõ hệ thống chưa bị thay đổi."
            )) {
                eprintln!(
                    "zkey-native: failure notification unavailable; see the startup error above"
                );
            }
        }
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_protocol_recovers_after_oversized_invalid_and_crlf_lines() {
        let mut input = vec![b'a'; 4096];
        input.extend_from_slice(b"\n\xff\naas\r\nhoaf");
        let mut output = Vec::new();
        line_protocol(std::io::Cursor::new(input), ToneStyle::Modern, &mut output).unwrap();
        assert_eq!(String::from_utf8(output).unwrap(), "!\n!\nấ\nhoà\n");
    }
    #[test]
    fn protocol_keeps_english_words_as_typed() {
        // The shell plugin sends the word before the cursor on every printable key.
        // Without a syllable check, ordinary command words come back mutated.
        let mut output = Vec::new();
        line_protocol(
            std::io::Cursor::new(b"status\nadd\nclass\ndd\n"),
            ToneStyle::Modern,
            &mut output,
        )
        .unwrap();
        assert_eq!(
            String::from_utf8(output).unwrap(),
            "status\nadd\nclass\nđ\n"
        );
    }
    #[test]
    fn protocol_lets_a_syllable_keep_composing_before_its_tone_arrives() {
        // Measured 22/11 in a terminal: `sawc` came back raw, so the following `s`
        // could never make "sắc". "săc" is a legitimate unfinished syllable.
        let mut output = Vec::new();
        line_protocol(
            std::io::Cursor::new(b"sawc\nsawcs\n"),
            ToneStyle::Modern,
            &mut output,
        )
        .unwrap();
        assert_eq!(String::from_utf8(output).unwrap(), "săc\nsắc\n");
    }
    #[test]
    fn protocol_honours_the_requested_tone_style() {
        let mut output = Vec::new();
        line_protocol(
            std::io::Cursor::new(b"hoas\nthuyr\n"),
            ToneStyle::Traditional,
            &mut output,
        )
        .unwrap();
        assert_eq!(String::from_utf8(output).unwrap(), "hóa\nthủy\n");
    }
}
