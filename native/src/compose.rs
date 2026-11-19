// SPDX-License-Identifier: AGPL-3.0-or-later
//! Word-local incremental Telex. Unicode scalars, not byte-indexed mutations.
use std::fmt;

pub const HARD_KEY_LIMIT: usize = 256;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ToneStyle {
    Modern,
    Traditional,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InputError {
    UnsupportedCharacter,
    TooLong,
}

impl fmt::Display for InputError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::UnsupportedCharacter => "Unsupported composition character (contents omitted)",
            Self::TooLong => "Composition key limit exceeded",
        })
    }
}

// Orthographic data, independent of the transport and UTF-8 byte offsets.
const ALPHABET: [&str; 12] = [
    "aáàảãạ",
    "ăắằẳẵặ",
    "âấầẩẫậ",
    "eéèẻẽẹ",
    "êếềểễệ",
    "iíìỉĩị",
    "oóòỏõọ",
    "ôốồổỗộ",
    "ơớờởỡợ",
    "uúùủũụ",
    "ưứừửữự",
    "yýỳỷỹỵ",
];

#[derive(Clone, Copy, Debug)]
struct Letter {
    plain: char,
    capital: bool,
}

impl Letter {
    fn decode(c: char) -> Option<(Self, usize)> {
        let lower = c.to_lowercase().next()?;
        for row in ALPHABET {
            if let Some(tone) = row.chars().position(|v| v == lower) {
                return Some((
                    Self {
                        plain: row.chars().next()?,
                        capital: c.is_uppercase(),
                    },
                    tone,
                ));
            }
        }
        (c.is_ascii_alphabetic() || lower == 'đ').then_some((
            Self {
                plain: lower,
                capital: c.is_uppercase(),
            },
            0,
        ))
    }
    fn vowel(self) -> bool {
        ALPHABET.iter().any(|row| row.starts_with(self.plain))
    }
    fn rendered(self, tone: usize) -> char {
        let glyph = ALPHABET
            .iter()
            .find(|row| row.starts_with(self.plain))
            .and_then(|row| row.chars().nth(tone))
            .unwrap_or(self.plain);
        if self.capital {
            glyph.to_uppercase().next().unwrap_or(glyph)
        } else {
            glyph
        }
    }
}

#[derive(Clone, Debug)]
pub struct Composer {
    raw: String,
    letters: Vec<Letter>,
    tone: usize,
    keys: usize,
    style: ToneStyle,
}

impl Composer {
    pub fn new(style: ToneStyle) -> Self {
        Self {
            raw: String::new(),
            letters: Vec::new(),
            tone: 0,
            keys: 0,
            style,
        }
    }
    pub fn raw(&self) -> &str {
        &self.raw
    }
    pub fn push(&mut self, key: char) -> Result<(), InputError> {
        if self.keys >= HARD_KEY_LIMIT {
            return Err(InputError::TooLong);
        }
        let (letter, existing_tone) =
            Letter::decode(key).ok_or(InputError::UnsupportedCharacter)?;
        self.raw.push(key);
        self.keys += 1;
        if !key.is_ascii() {
            self.letters.push(letter);
            if existing_tone != 0 {
                self.tone = existing_tone;
            }
            return Ok(());
        }
        let mark = match letter.plain {
            's' => 1,
            'f' => 2,
            'r' => 3,
            'x' => 4,
            'j' => 5,
            _ => 0,
        };
        if mark != 0 && self.tone_position().is_some() {
            if self.tone == mark {
                self.tone = 0;
                self.letters.push(letter);
            } else {
                self.tone = mark;
            }
        } else if letter.plain == 'z' && self.tone != 0 {
            self.tone = 0;
        } else if !self.reshape(letter) {
            self.letters.push(letter);
        }
        Ok(())
    }
    fn reshape(&mut self, key: Letter) -> bool {
        if key.plain == 'd' {
            if let Some(last) = self.letters.last_mut() {
                match last.plain {
                    'd' => {
                        last.plain = 'đ';
                        return true;
                    }
                    'đ' => {
                        last.plain = 'd';
                        self.letters.push(key);
                        return true;
                    }
                    _ => {}
                }
            }
            return false;
        }
        if let Some((from, shaped)) = match key.plain {
            'a' => Some(('a', 'â')),
            'e' => Some(('e', 'ê')),
            'o' => Some(('o', 'ô')),
            _ => None,
        } {
            // Late shape is permitted across a final consonant, not another vowel.
            if let Some(last_vowel) = self.letters.iter_mut().rev().find(|letter| letter.vowel()) {
                if last_vowel.plain == from {
                    last_vowel.plain = shaped;
                    return true;
                }
                if last_vowel.plain == shaped {
                    last_vowel.plain = from;
                    self.letters.push(key);
                    return true;
                }
            }
        }
        if key.plain != 'w' {
            return false;
        }
        let Some(at) = self
            .letters
            .iter()
            .rposition(|letter| "aăoơuư".contains(letter.plain))
        else {
            return false;
        };
        let previous_u = at
            .checked_sub(1)
            .filter(|&i| "uư".contains(self.letters[i].plain))
            .filter(|&i| i == 0 || self.letters[i - 1].plain != 'q');
        let value = self.letters[at].plain;
        if value == 'a'
            && let Some(before) = previous_u
        {
            let undo = self.letters[before].plain == 'ư';
            self.letters[before].plain = if undo { 'u' } else { 'ư' };
            if undo {
                self.letters.push(key);
            }
            return true;
        }
        let (replacement, undo) = match value {
            'a' => ('ă', false),
            'ă' => ('a', true),
            'o' => ('ơ', false),
            'ơ' => ('o', true),
            'u' => ('ư', false),
            'ư' => ('u', true),
            _ => return false,
        };
        self.letters[at].plain = replacement;
        if matches!(value, 'o' | 'ơ')
            && let Some(before) = previous_u
        {
            self.letters[before].plain = if undo { 'u' } else { 'ư' };
        }
        if undo {
            self.letters.push(key);
        }
        true
    }
    fn tone_position(&self) -> Option<usize> {
        let mut vowels: Vec<usize> = self
            .letters
            .iter()
            .enumerate()
            .filter_map(|(i, letter)| letter.vowel().then_some(i))
            .collect();
        if vowels.len() >= 2 {
            let first = vowels[0];
            if first > 0
                && matches!(
                    (self.letters[first - 1].plain, self.letters[first].plain),
                    ('q', 'u') | ('g', 'i')
                )
            {
                vowels.remove(0);
            }
        }
        if let Some(&at) = vowels
            .iter()
            .rev()
            .find(|&&at| "êơ".contains(self.letters[at].plain))
        {
            return Some(at);
        }
        match vowels.as_slice() {
            [] => None,
            [at] => Some(*at),
            [a, b] => {
                let pair = (self.letters[*a].plain, self.letters[*b].plain);
                let second = *b + 1 < self.letters.len()
                    || (self.style == ToneStyle::Modern
                        && matches!(pair, ('o', 'a') | ('o', 'e') | ('u', 'y')));
                Some(if second { *b } else { *a })
            }
            _ => Some(vowels[vowels.len() - 2]),
        }
    }
    pub fn text(&self) -> String {
        let at = self.tone_position();
        self.letters
            .iter()
            .enumerate()
            .map(|(i, letter)| letter.rendered(if Some(i) == at { self.tone } else { 0 }))
            .collect()
    }
}

// Orthographic shapes used only to keep non-Vietnamese words as typed by the
// shell line protocol. Kept beside the alphabet so both agree on what a vowel is.
const ONSETS: [&str; 27] = [
    "ngh", "ng", "nh", "ch", "gh", "kh", "ph", "th", "tr", "b", "c", "d", "đ", "g", "h", "k", "l",
    "m", "n", "p", "q", "r", "s", "t", "v", "x", "",
];
const NUCLEI: &[&str] = &[
    "a", "ă", "â", "e", "ê", "i", "o", "ô", "ơ", "u", "ư", "y", "ai", "ao", "au", "ay", "âu", "ây",
    "eo", "êu", "ia", "iê", "iu", "oa", "oă", "oe", "oi", "oo", "ôi", "ơi", "ua", "uâ", "uê", "ui",
    "uô", "uơ", "uy", "ưa", "ưi", "ươ", "ưu", "yê", "iêu", "yêu", "oai", "oay", "oeo", "uây",
    "uôi", "ươi", "ươu", "uya", "uyê", "uyu",
];
const CODAS: [&str; 9] = ["", "c", "ch", "m", "n", "ng", "nh", "p", "t"];

fn base_of(c: char) -> char {
    Letter::decode(c).map_or(c, |(letter, _)| letter.plain)
}

/// Plausible (possibly still being typed) Vietnamese syllable: onset, vowel
/// nucleus from the Vietnamese set, final consonant. The shell line protocol
/// uses it to keep English/command words as typed ("status" must not become
/// "státu"). It is a spelling-shape check, not a dictionary.
pub fn valid_syllable(word: &str) -> bool {
    let chars: Vec<char> = word.chars().map(base_of).collect();
    let text: String = chars.iter().collect();
    let next_is_vowel = |at: usize| {
        chars
            .get(at)
            .is_some_and(|c| Letter::decode(*c).is_some_and(|(l, _)| l.vowel()))
    };
    // "gi"+vowel and "qu" act as one onset ("giá", "quá"); bare "gì" is g + i.
    let onset_len = if (text.starts_with("gi") && next_is_vowel(2)) || text.starts_with("qu") {
        2
    } else {
        ONSETS
            .iter()
            .find(|onset| text.starts_with(*onset))
            .map_or(0, |onset| onset.chars().count())
    };
    let rest = &chars[onset_len..];
    if rest.is_empty() {
        return true; // Only an onset so far, or nothing.
    }
    let nucleus_len = rest
        .iter()
        .take_while(|c| Letter::decode(**c).is_some_and(|(l, _)| l.vowel()))
        .count();
    if nucleus_len == 0 {
        return false;
    }
    let nucleus: String = rest[..nucleus_len].iter().collect();
    let coda: String = rest[nucleus_len..].iter().collect();
    NUCLEI.contains(&nucleus.as_str()) && CODAS.contains(&coda.as_str())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn word(raw: &str, style: ToneStyle) -> String {
        let mut c = Composer::new(style);
        for key in raw.chars() {
            c.push(key).unwrap();
        }
        c.text()
    }
    #[test]
    fn visible_prefixes_are_incremental() {
        let mut c = Composer::new(ToneStyle::Modern);
        for (key, expected) in "tieengs"
            .chars()
            .zip(["t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng"])
        {
            c.push(key).unwrap();
            assert_eq!(c.text(), expected);
        }
        assert_eq!(c.raw(), "tieengs");
    }
    #[test]
    fn alphabet_and_every_tone_preserve_case() {
        for (raw, forms) in [
            ("a", "aáàảãạ"),
            ("aw", "ăắằẳẵặ"),
            ("aa", "âấầẩẫậ"),
            ("e", "eéèẻẽẹ"),
            ("ee", "êếềểễệ"),
            ("i", "iíìỉĩị"),
            ("o", "oóòỏõọ"),
            ("oo", "ôốồổỗộ"),
            ("ow", "ơớờởỡợ"),
            ("u", "uúùủũụ"),
            ("uw", "ưứừửữự"),
            ("y", "yýỳỷỹỵ"),
        ] {
            for (mark, expected) in ["", "s", "f", "r", "x", "j"].into_iter().zip(forms.chars()) {
                let keys = format!("{raw}{mark}");
                assert_eq!(word(&keys, ToneStyle::Modern), expected.to_string());
                assert_eq!(
                    word(&keys.to_uppercase(), ToneStyle::Modern),
                    expected.to_uppercase().to_string()
                );
            }
        }
    }
    #[test]
    fn horn_pairs_and_qu_onset() {
        for (raw, text) in [
            ("thuowngr", "thưởng"),
            ("thuwowngr", "thưởng"),
            ("muaw", "mưa"),
            ("chuaw", "chưa"),
            ("quawng", "quăng"),
            ("quowr", "quở"),
            ("nguawj", "ngựa"),
        ] {
            assert_eq!(word(raw, ToneStyle::Modern), text, "{raw}");
        }
    }
    #[test]
    fn late_shape_keys_reach_the_vowel_before_the_coda() {
        for (raw, text) in [("tienegs", "tiếng"), ("dduongwf", "đường"), ("banw", "băn")] {
            assert_eq!(word(raw, ToneStyle::Modern), text, "{raw}");
        }
    }
    #[test]
    fn tone_placement_accounts_for_onsets_and_codas() {
        for (raw, text) in [
            ("quas", "quá"),
            ("gias", "giá"),
            ("gif", "gì"),
            ("khuyar", "khuỷa"),
            ("nguyeenx", "nguyễn"),
            ("hoasn", "hoán"),
        ] {
            assert_eq!(word(raw, ToneStyle::Modern), text, "{raw}");
        }
        assert_eq!(word("hoas", ToneStyle::Traditional), "hóa");
        assert_eq!(word("hoas", ToneStyle::Modern), "hoá");
        assert_eq!(word("thuyr", ToneStyle::Traditional), "thủy");
    }
    #[test]
    fn repeated_modifiers_restore_literal_input() {
        for (raw, text) in [
            ("ass", "as"),
            ("aaa", "aa"),
            ("ddd", "dd"),
            ("uoww", "uow"),
            ("muaww", "muaw"),
            ("asf", "à"),
            ("asz", "a"),
            ("dd", "đ"),
        ] {
            assert_eq!(word(raw, ToneStyle::Modern), text, "{raw}");
        }
    }
    #[test]
    fn nfc_continuation_retains_and_changes_tone() {
        for (raw, text) in [
            ("đườns", "đướn"),
            ("áf", "à"),
            ("ás", "as"),
            ("ĐƯỜNG", "ĐƯỜNG"),
        ] {
            assert_eq!(word(raw, ToneStyle::Modern), text, "{raw}");
        }
    }
    #[test]
    fn syllable_check_accepts_vietnamese_rejects_english_shapes() {
        for word in [
            "tiếng",
            "Việt",
            "Điện",
            "đường",
            "được",
            "nguyễn",
            "thưởng",
            "quá",
            "giá",
            "gì",
            "nghiêng",
            "NGUYỄN",
            "ắ",
            "mưa",
            "quăng",
            "hoà",
            "thuỷ",
            "khuya",
            "oanh",
            "ạ",
            "tiê",
            "tiên",
            "ngh",
            "t",
            "",
        ] {
            assert!(valid_syllable(word), "{word}");
        }
        for word in [
            "statú", "ađ", "clá", "đd", "stá", "ăb", "tứo", "aaaá", "ês", "clas",
        ] {
            assert!(!valid_syllable(word), "{word}");
        }
    }
    #[test]
    fn invalid_input_is_rejected_without_mutating_the_word() {
        let mut c = Composer::new(ToneStyle::Modern);
        c.push('a').unwrap();
        for invalid in ['\0', '\n', ' ', '🙂', '\u{301}'] {
            assert_eq!(c.push(invalid), Err(InputError::UnsupportedCharacter));
            assert_eq!(c.raw(), "a");
        }
    }
    #[test]
    fn hard_limit_has_a_real_boundary() {
        let mut c = Composer::new(ToneStyle::Modern);
        for _ in 0..HARD_KEY_LIMIT {
            c.push('b').unwrap();
        }
        assert_eq!(c.push('a'), Err(InputError::TooLong));
        assert_eq!(c.raw().len(), HARD_KEY_LIMIT);
    }
}
