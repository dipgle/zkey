pub const MAX_KEYS: usize = 256;

// Each row: plain, acute, grave, hook, tilde, dot. NFC Unicode, no runtime normalization.
const VOWELS: [&str; 12] = [
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

fn lower(c: char) -> char {
    c.to_lowercase().next().unwrap_or(c)
}

fn with_case(original: char, replacement: char) -> char {
    if original.is_uppercase() {
        replacement.to_uppercase().next().unwrap_or(replacement)
    } else {
        replacement
    }
}

fn is_vowel(c: char) -> bool {
    VOWELS.iter().any(|row| row.starts_with(lower(c)))
}

pub fn is_vietnamese(c: char) -> bool {
    let c = lower(c);
    c == 'đ' || VOWELS.iter().any(|row| row.contains(c))
}

fn tone_index(word: &[char], modern: bool) -> Option<usize> {
    let mut indices: Vec<usize> = word
        .iter()
        .enumerate()
        .filter_map(|(i, &c)| is_vowel(c).then_some(i))
        .collect();
    if indices.len() > 1 {
        let first = indices[0];
        if first > 0
            && ((lower(word[first - 1]) == 'q' && lower(word[first]) == 'u')
                || (lower(word[first - 1]) == 'g' && lower(word[first]) == 'i'))
        {
            indices.remove(0);
        }
    }
    // In ươ, the tone belongs on ơ. Other ê/ơ take priority over unmarked vowels.
    if let Some(&i) = indices
        .iter()
        .rev()
        .find(|&&i| matches!(lower(word[i]), 'ê' | 'ơ'))
    {
        return Some(i);
    }
    match indices.len() {
        0 => None,
        1 => Some(indices[0]),
        2 => {
            let pair: String = indices.iter().map(|&i| lower(word[i])).collect();
            let closed = indices[1] + 1 < word.len();
            Some(
                indices[usize::from(
                    closed || (modern && matches!(pair.as_str(), "oa" | "oe" | "uy")),
                )],
            )
        }
        _ => Some(indices[indices.len() - 2]),
    }
}

fn shape(word: &mut Vec<char>, key: char) -> bool {
    let k = lower(key);
    if matches!(k, 'a' | 'e' | 'o' | 'd')
        && let Some(last) = word.last_mut()
    {
        let pair = match k {
            'a' => ('a', 'â'),
            'e' => ('e', 'ê'),
            'o' => ('o', 'ô'),
            _ => ('d', 'đ'),
        };
        if lower(*last) == pair.0 {
            *last = with_case(*last, pair.1);
            return true;
        }
        if lower(*last) == pair.1 {
            *last = with_case(*last, pair.0);
            word.push(key);
            return true;
        }
    }
    if k != 'w' {
        return false;
    }
    let Some(i) = word
        .iter()
        .rposition(|&c| matches!(lower(c), 'a' | 'ă' | 'o' | 'ơ' | 'u' | 'ư'))
    else {
        return false;
    };
    let has_u =
        i > 0 && matches!(lower(word[i - 1]), 'u' | 'ư') && !(i > 1 && lower(word[i - 2]) == 'q');
    let c = lower(word[i]);
    // ua + w is ưa; after q the u is an onset, so quaw remains quă.
    if has_u && c == 'a' {
        let undo = lower(word[i - 1]) == 'ư';
        word[i - 1] = with_case(word[i - 1], if undo { 'u' } else { 'ư' });
        if undo {
            word.push(key);
        }
        return true;
    }
    let replacement = match c {
        'a' => 'ă',
        'o' => 'ơ',
        'u' => 'ư',
        'ă' => 'a',
        'ơ' => 'o',
        'ư' => 'u',
        _ => unreachable!(),
    };
    word[i] = with_case(word[i], replacement);
    if has_u && matches!(c, 'o' | 'ơ') {
        word[i - 1] = with_case(word[i - 1], if c == 'o' { 'ư' } else { 'u' });
    }
    if matches!(c, 'ă' | 'ơ' | 'ư') {
        word.push(key);
    }
    true
}

/// Replay a single ASCII word. Callers bound input to MAX_KEYS on the interactive path.
pub fn compose(raw: &str, modern: bool) -> String {
    let mut word = Vec::with_capacity(raw.len());
    let mut tone = 0;
    for key in raw.chars() {
        // Editing can leave NFC Vietnamese in the buffer. Recover its base and
        // tone so subsequent Telex keys still move/replace the tone normally.
        if !key.is_ascii()
            && let Some(row) = VOWELS.iter().find(|row| row.contains(lower(key)))
        {
            let mark = row.chars().position(|c| c == lower(key)).unwrap();
            if mark != 0 {
                tone = mark;
            }
            word.push(with_case(key, row.chars().next().unwrap()));
            continue;
        }
        let requested = match lower(key) {
            's' => 1,
            'f' => 2,
            'r' => 3,
            'x' => 4,
            'j' => 5,
            _ => 0,
        };
        if requested > 0 && tone_index(&word, modern).is_some() {
            if tone == requested {
                tone = 0;
                word.push(key);
            } else {
                tone = requested;
            }
        } else if lower(key) == 'z' && tone != 0 {
            tone = 0;
        } else if !shape(&mut word, key) {
            word.push(key);
        }
    }
    if tone != 0
        && let Some(i) = tone_index(&word, modern)
    {
        let row = VOWELS
            .iter()
            .find(|row| row.starts_with(lower(word[i])))
            .unwrap();
        word[i] = with_case(word[i], row.chars().nth(tone).unwrap());
    }
    word.into_iter().collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vietnamese_words() {
        let cases = [
            ("tieengs", "tiếng"),
            ("Vieetj", "Việt"),
            ("DDieenj", "Điện"),
            ("dduwowngf", "đường"),
            ("dduwowcj", "được"),
            ("nguyeenx", "nguyễn"),
            ("thuwowngr", "thưởng"),
            ("thuowngr", "thưởng"),
            ("tuowngr", "tưởng"),
            ("quas", "quá"),
            ("quowr", "quở"),
            ("gias", "giá"),
            ("gif", "gì"),
            ("nghieeng", "nghiêng"),
            ("nghieengx", "nghiễng"),
            ("NGUYEENX", "NGUYỄN"),
            ("aws", "ắ"),
            ("aas", "ấ"),
            ("ees", "ế"),
            ("oos", "ố"),
            ("ows", "ớ"),
            ("uws", "ứ"),
            ("muaw", "mưa"),
            ("cuaw", "cưa"),
            ("chuaw", "chưa"),
            ("nguawj", "ngựa"),
            ("MUAW", "MƯA"),
            ("quawng", "quăng"),
            ("muaww", "muaw"),
        ];
        for (raw, expected) in cases {
            assert_eq!(compose(raw, true), expected, "{raw}");
        }
    }

    #[test]
    fn tone_moves_when_coda_arrives() {
        assert_eq!(compose("hoas", false), "hóa");
        assert_eq!(compose("hoasn", false), "hoán");
        assert_eq!(compose("hoaf", true), "hoà");
        assert_eq!(compose("thuyr", true), "thuỷ");
        assert_eq!(compose("thuyr", false), "thủy");
    }

    #[test]
    fn undo_and_replace() {
        for (raw, expected) in [
            ("ass", "as"),
            ("aaa", "aa"),
            ("ddd", "dd"),
            ("oww", "ow"),
            ("uoww", "uow"),
            ("asf", "à"),
            ("asz", "a"),
            ("stress", "stres"),
        ] {
            assert_eq!(compose(raw, true), expected, "{raw}");
        }
    }

    #[test]
    fn all_tones_all_vowels_and_cases() {
        let raw = [
            "a", "aw", "aa", "e", "ee", "i", "o", "oo", "ow", "u", "uw", "y",
        ];
        for (base, row) in raw.iter().zip(VOWELS) {
            for (key, expected) in ["", "s", "f", "r", "x", "j"].iter().zip(row.chars()) {
                let input = format!("{base}{key}");
                assert_eq!(compose(&input, true), expected.to_string());
                assert_eq!(
                    compose(&input.to_uppercase(), true),
                    expected.to_uppercase().to_string()
                );
            }
        }
    }

    #[test]
    fn every_prefix_can_be_replayed_after_backspace() {
        let raw = "dduwowngf";
        let expected = [
            "",
            "d",
            "đ",
            "đu",
            "đư",
            "đưo",
            "đươ",
            "đươn",
            "đương",
            "đường",
        ];
        for (n, value) in expected.iter().enumerate() {
            assert_eq!(compose(&raw[..n], true), *value);
        }
    }

    #[test]
    fn continue_editing_composed_vietnamese() {
        for (raw, expected) in [
            ("đườn", "đườn"),
            ("đường", "đường"),
            ("đườns", "đướn"),
            ("ĐƯỜNG", "ĐƯỜNG"),
            ("áf", "à"),
            ("ás", "as"),
        ] {
            assert_eq!(compose(raw, true), expected, "{raw}");
        }
    }
}
