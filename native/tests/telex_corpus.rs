// SPDX-License-Identifier: AGPL-3.0-or-later
//! Orthography corpus for the native composer (N06). Oracle = hand-written
//! Vietnamese spelling in telex_corpus.txt, never output of the composer.
use zkey_native::compose::{Composer, ToneStyle};

const CORPUS: &str = include_str!("telex_corpus.txt");

struct Case<'a> {
    line: usize,
    styles: &'static [ToneStyle],
    keys: &'a str,
    expected: &'a str,
}

fn parse(text: &str) -> Result<Vec<Case<'_>>, String> {
    let mut cases = Vec::new();
    for (index, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = line.split_whitespace().collect();
        let [style, keys, expected] = fields[..] else {
            return Err(format!("line {}: expected 3 fields", index + 1));
        };
        let styles: &'static [ToneStyle] = match style {
            "m" => &[ToneStyle::Modern],
            "t" => &[ToneStyle::Traditional],
            "*" => &[ToneStyle::Modern, ToneStyle::Traditional],
            _ => return Err(format!("line {}: unknown style", index + 1)),
        };
        if !keys.is_ascii() || !keys.chars().all(|c| c.is_ascii_alphabetic()) {
            return Err(format!("line {}: keys must be ASCII letters", index + 1));
        }
        cases.push(Case {
            line: index + 1,
            styles,
            keys,
            expected,
        });
    }
    Ok(cases)
}

fn compose(keys: &str, style: ToneStyle) -> Result<String, String> {
    let mut word = Composer::new(style);
    for key in keys.chars() {
        word.push(key).map_err(|e| e.to_string())?;
    }
    Ok(word.text())
}

/// Every mismatch, never only the first: the report is the measurement.
fn mismatches(cases: &[Case<'_>]) -> (usize, Vec<String>) {
    let mut checked = 0;
    let mut failed = Vec::new();
    for case in cases {
        for &style in case.styles {
            checked += 1;
            match compose(case.keys, style) {
                Ok(text) if text == case.expected => {}
                Ok(text) => failed.push(format!(
                    "line {} {style:?}: {} => {text} (want {})",
                    case.line, case.keys, case.expected
                )),
                Err(error) => failed.push(format!("line {} {style:?}: {error}", case.line)),
            }
        }
    }
    (checked, failed)
}

#[test]
fn corpus_matches_vietnamese_orthography() {
    let cases = parse(CORPUS).expect("corpus must parse completely");
    let (checked, failed) = mismatches(&cases);
    // Denominator: a truncated or emptied corpus must not pass as green.
    assert!(
        cases.len() >= 130,
        "corpus shrank to {} entries",
        cases.len()
    );
    assert!(checked >= cases.len());
    assert!(
        failed.is_empty(),
        "{}/{checked} corpus checks failed:\n{}",
        failed.len(),
        failed.join("\n")
    );
}

#[test]
fn checker_turns_red_on_wrong_oracle_and_bad_lines() {
    // Inverse control: a known-wrong expectation must be reported.
    let wrong = parse("m hoaf hòa\n* tieengs tieng\n").unwrap();
    let (checked, failed) = mismatches(&wrong);
    assert_eq!((checked, failed.len()), (3, 3), "{failed:?}");
    // And a correct pair must stay green under the same checker.
    let right = parse("m hoaf hoà\nt hoaf hòa\n").unwrap();
    assert_eq!(mismatches(&right).1, Vec::<String>::new());
    for bad in ["* tieengs", "x tieengs tiếng", "* tiê tiê", "* a b c d"] {
        assert!(parse(bad).is_err(), "{bad} must be rejected");
    }
}
