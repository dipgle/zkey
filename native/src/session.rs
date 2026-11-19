// SPDX-License-Identifier: AGPL-3.0-or-later
//! Transport-independent state. A snapshot is evidence of text, NOT proof that
//! a later deletion will work. Legacy rewrites therefore require explicit opt-in.
use crate::compose::{Composer, HARD_KEY_LIMIT, ToneStyle};

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Edit {
    pub handled: bool,
    pub remove: u32,
    pub insert: String,
}

#[derive(Clone, Debug)]
struct Snapshot {
    before: Vec<char>,
    cursor: usize,
    selection: bool,
}
#[derive(Debug)]
struct BackspaceTicket {
    before: Vec<char>,
    cursor: usize,
    visible: String,
    origin: usize,
    literal: bool,
}
#[derive(Debug)]
struct PendingSpan {
    visible: String,
    wanted: String,
    origin: Option<usize>,
}

#[derive(Debug)]
pub struct Session {
    style: ToneStyle,
    pub enabled: bool,
    capable: bool,
    protected: bool,
    rewrite_allowed: bool,
    snapshot: Option<Snapshot>,
    word: Composer,
    visible: String,
    origin: Option<usize>,
    literal: bool,
    bypass: bool,
    max_keys: usize,
    native_backspace: Option<BackspaceTicket>,
    pending: Option<PendingSpan>,
    reset_pending: bool,
}

impl Session {
    pub fn new(
        style: ToneStyle,
        enabled: bool,
        max_keys: usize,
        experimental_rewrite: bool,
    ) -> Self {
        Self {
            style,
            enabled,
            capable: false,
            protected: true,
            rewrite_allowed: experimental_rewrite,
            snapshot: None,
            word: Composer::new(style),
            visible: String::new(),
            origin: None,
            literal: false,
            bypass: false,
            max_keys: max_keys.clamp(8, HARD_KEY_LIMIT),
            native_backspace: None,
            pending: None,
            reset_pending: false,
        }
    }
    pub fn reset(&mut self) {
        self.word = Composer::new(self.style);
        self.visible.clear();
        self.origin = None;
        self.literal = false;
        self.bypass = false;
        self.snapshot = None;
        self.native_backspace = None;
        self.pending = None;
        self.reset_pending = false;
    }
    pub fn client_reset(&mut self) {
        // GTK resets its IM context as part of its own native Backspace path,
        // and some clients (measured: Firefox) reset after every commit. Keep
        // the word only until the next surrounding text proves it is still in
        // the field; otherwise the next snapshot discards it.
        let ticket = self.native_backspace.take();
        self.snapshot = None;
        self.reset_pending = true;
        self.native_backspace = ticket;
    }
    pub fn leave_context(&mut self) {
        self.reset();
        self.protected = true;
    }
    pub fn configure(&mut self, config: &crate::config::Config, experimental: bool) {
        self.style = config.style;
        self.enabled = config.enabled;
        self.max_keys = config.max_word_keys;
        self.rewrite_allowed = experimental || config.experimental_rewrite;
        self.reset();
    }
    pub fn capabilities(&mut self, caps: u32) {
        self.capable = caps & (1 << 5) != 0;
        if !self.capable {
            self.reset();
        }
    }
    pub fn content(&mut self, purpose: u32, hints: u32) {
        // Public IBus purposes 0..7 are non-secret. PASSWORD/PIN/TERMINAL and
        // any future/unknown purpose stay closed until explicitly supported.
        self.protected = !matches!(purpose, 0..=7) || hints & ((1 << 11) | (1 << 12)) != 0;
        if self.protected {
            self.reset();
        }
    }
    pub fn protected(&self) -> bool {
        self.protected
    }
    pub fn accepts(&self) -> bool {
        self.enabled && self.capable && !self.protected && self.rewrite_allowed
    }
    pub fn snapshot(&mut self, text: &str, cursor: usize, anchor: usize) -> Edit {
        if !self.accepts() {
            self.snapshot = None;
            return Edit::default();
        }
        let count = text.chars().count();
        if cursor > count || anchor > count {
            self.reset();
            return Edit::default();
        }
        // Keep at most our hard word bound + a boundary, not the whole document.
        let before = text.chars().take(cursor).collect::<Vec<_>>();
        let before = before[before.len().saturating_sub(HARD_KEY_LIMIT + 1)..].to_vec();
        self.snapshot = Some(Snapshot {
            before,
            cursor,
            selection: cursor != anchor,
        });
        if self.reset_pending {
            self.reset_pending = false;
            // The client reset its context, but some clients (measured: Firefox)
            // do that after every commit. Continue the same word only when the
            // surrounding text proves it is still there at the same caret.
            if !self.owns() {
                self.reset();
                return self.snapshot(text, cursor, anchor);
            }
        }
        if let Some(ticket) = self.native_backspace.take() {
            let matches = self.snapshot.as_ref().is_some_and(|s| {
                !s.selection && s.cursor == ticket.cursor && s.before.ends_with(&ticket.before)
            });
            if matches {
                self.word = Composer::new(self.style);
                for c in ticket.visible.chars() {
                    if self.word.push(c).is_err() {
                        self.reset();
                        return Edit::default();
                    }
                }
                self.visible = ticket.visible;
                self.origin = Some(ticket.origin);
                self.literal = ticket.literal;
            } else {
                // A pre-deletion snapshot can arrive before the native edit.
                // The next key/focus/shortcut discards an unproven ticket.
                self.native_backspace = Some(ticket);
            }
        }
        if let Some(pending) = &self.pending {
            let visible = format!("{}{}", pending.visible, self.visible);
            let word = if self.literal {
                self.visible.clone()
            } else {
                self.word.text()
            };
            let wanted = format!("{}{}", pending.wanted, word);
            let chars: Vec<_> = visible.chars().collect();
            let confirmed = self
                .snapshot
                .as_ref()
                .filter(|s| !s.selection && chars.len() <= s.cursor && s.before.ends_with(&chars))
                .filter(|s| {
                    pending
                        .origin
                        .is_none_or(|origin| s.cursor - chars.len() == origin)
                })
                .filter(|s| {
                    let at = s.before.len() - chars.len();
                    at == 0 || !s.before[at - 1].is_alphabetic()
                })
                .map(|s| s.cursor - chars.len());
            if let Some(start) = confirmed {
                self.origin = Some(start + pending.wanted.chars().count());
                self.pending = None;
                if wanted != visible {
                    let common = visible
                        .chars()
                        .zip(wanted.chars())
                        .take_while(|(a, b)| a == b)
                        .count();
                    self.visible = word;
                    self.snapshot = None;
                    return Edit {
                        handled: true,
                        remove: (chars.len() - common) as u32,
                        insert: wanted.chars().skip(common).collect(),
                    };
                }
            }
        }
        if self.owns() && !self.literal {
            let wanted = self.word.text();
            if wanted != self.visible {
                return self.replacement(wanted);
            }
        }
        Edit::default()
    }
    fn owns(&self) -> bool {
        let Some(s) = &self.snapshot else {
            return false;
        };
        let word: Vec<_> = self.visible.chars().collect();
        if word.is_empty() || s.selection || word.len() > s.before.len() || word.len() > s.cursor {
            return false;
        }
        let at = s.before.len() - word.len();
        if s.before[at..] != word || (at > 0 && s.before[at - 1].is_alphabetic()) {
            return false;
        }
        self.origin
            .is_none_or(|origin| s.cursor - word.len() == origin)
    }
    fn replacement(&mut self, wanted: String) -> Edit {
        let common = self
            .visible
            .chars()
            .zip(wanted.chars())
            .take_while(|(a, b)| a == b)
            .count();
        let remove = self.visible.chars().count() - common;
        let insert = wanted.chars().skip(common).collect();
        if let Some(s) = &self.snapshot {
            self.origin = Some(s.cursor - self.visible.chars().count());
        }
        self.visible = wanted;
        self.snapshot = None; // Never regard libibus's optimistic cache as an ACK.
        Edit {
            handled: true,
            remove: remove as u32,
            insert,
        }
    }
    pub fn freeze(&mut self) {
        self.native_backspace = None;
        // Ctrl freezes the text already visible, not the older Telex keys that
        // produced it. Escape must not undo across that explicit boundary.
        self.word = Composer::new(self.style);
        for key in self.visible.chars() {
            if self.word.push(key).is_err() {
                self.reset();
                return;
            }
        }
        self.literal = true;
    }
    pub fn key(&mut self, key: char) -> Edit {
        self.native_backspace = None;
        if !self.accepts() {
            self.reset();
            return Edit::default();
        }
        if self.reset_pending {
            // No surrounding text confirmed the word after the client's reset.
            self.reset();
        }
        if self.snapshot.as_ref().is_some_and(|s| s.selection) {
            self.reset();
            return Edit::default();
        }
        if !key.is_alphabetic() || Composer::new(self.style).push(key).is_err() {
            let wanted = if self.literal {
                self.visible.clone()
            } else {
                self.word.text()
            };
            let pending = if self.pending.is_some() || wanted != self.visible {
                let previous = self.pending.take().unwrap_or(PendingSpan {
                    visible: String::new(),
                    wanted: String::new(),
                    origin: self.origin,
                });
                let visible = format!("{}{}{key}", previous.visible, self.visible);
                let wanted = format!("{}{wanted}{key}", previous.wanted);
                // Match the bounded snapshot window; overflow keeps committed
                // keys literal instead of retaining unbounded document text.
                (visible.chars().count() <= HARD_KEY_LIMIT).then_some(PendingSpan {
                    visible,
                    wanted,
                    origin: previous.origin,
                })
            } else {
                None
            };
            self.reset();
            self.pending = pending;
            return Edit {
                handled: true,
                insert: key.to_string(),
                ..Edit::default()
            };
        }
        if self.bypass || self.word.raw().chars().count() >= self.max_keys {
            self.reset();
            self.bypass = true;
            return Edit {
                handled: true,
                insert: key.to_string(),
                ..Edit::default()
            };
        }
        let owned = self.owns();
        if self.visible.is_empty() {
            self.origin = self
                .snapshot
                .as_ref()
                .filter(|s| !s.selection)
                .map(|s| s.cursor);
        }
        // Validated above and bounded here; preserve the key if a future core
        // validation rule rejects it instead of panicking across the ABI.
        if self.word.push(key).is_err() {
            self.reset();
            return Edit {
                handled: true,
                insert: key.to_string(),
                ..Edit::default()
            };
        }
        if owned && !self.literal {
            return self.replacement(self.word.text());
        }
        self.visible.push(key);
        self.snapshot = None;
        Edit {
            handled: true,
            insert: key.to_string(),
            ..Edit::default()
        }
    }
    pub fn backspace(&mut self) {
        let ticket = if self.owns() {
            self.snapshot.as_ref().and_then(|s| {
                let mut before = s.before.clone();
                before.pop()?;
                let mut visible = self.visible.clone();
                visible.pop()?;
                if visible.is_empty() {
                    return None;
                }
                Some(BackspaceTicket {
                    before,
                    cursor: s.cursor.checked_sub(1)?,
                    origin: s.cursor - self.visible.chars().count(),
                    visible,
                    literal: self.literal,
                })
            })
        } else {
            None
        };
        self.visible.pop();
        self.word = Composer::new(self.style);
        for key in self.visible.chars() {
            if self.word.push(key).is_err() {
                self.reset();
                return;
            }
        }
        self.snapshot = None;
        self.native_backspace = ticket;
    }
    pub fn escape(&mut self) -> Edit {
        if !self.accepts() || !self.owns() {
            self.reset();
            return Edit::default();
        }
        let edit = self.replacement(self.word.raw().to_owned());
        self.literal = true;
        edit
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Editor {
        s: Session,
        text: String,
    }
    impl Editor {
        fn new() -> Self {
            let mut s = Session::new(ToneStyle::Modern, true, 256, true);
            s.capabilities(32);
            s.content(0, 0);
            Self {
                s,
                text: String::new(),
            }
        }
        fn apply(&mut self, edit: Edit) {
            for _ in 0..edit.remove {
                self.text.pop();
            }
            self.text.push_str(&edit.insert);
        }
        fn key(&mut self, k: char) {
            let n = self.text.chars().count();
            let ack = self.s.snapshot(&self.text, n, n);
            self.apply(ack);
            let edit = self.s.key(k);
            self.apply(edit);
        }
    }
    #[test]
    fn doubled_mark_key_is_the_classic_telex_undo_in_the_real_edit_flow() {
        // Hà 19/11: "cuss" gives "cus" (the second s undoes the tone and is not doubled);
        // "cứ" is typed cuws. Checked through delete+commit, not only the core.
        let mut e = Editor::new();
        for (k, text) in "cuss".chars().zip(["c", "cu", "cú", "cus"]) {
            e.key(k);
            assert_eq!(e.text, text);
        }
        let mut e = Editor::new();
        for (k, text) in "cuws".chars().zip(["c", "cu", "cư", "cứ"]) {
            e.key(k);
            assert_eq!(e.text, text);
        }
    }
    #[test]
    fn legacy_rewrite_is_never_enabled_implicitly() {
        let mut s = Session::new(ToneStyle::Modern, true, 256, false);
        s.capabilities(32);
        s.content(0, 0);
        assert!(!s.key('a').handled);
        assert!(!s.key('s').handled);
    }
    #[test]
    fn acknowledged_prefixes_and_boundaries_do_not_duplicate() {
        let mut e = Editor::new();
        for (k, text) in "tieengs vieetj".chars().zip([
            "t",
            "ti",
            "tie",
            "tiê",
            "tiên",
            "tiêng",
            "tiếng",
            "tiếng ",
            "tiếng v",
            "tiếng vi",
            "tiếng vie",
            "tiếng viê",
            "tiếng viêt",
            "tiếng việt",
        ]) {
            e.key(k);
            assert_eq!(e.text, text);
        }
    }
    #[test]
    fn unacknowledged_burst_is_inserted_in_order_then_composed() {
        let mut e = Editor::new();
        for key in "tieengs".chars() {
            let edit = e.s.key(key);
            assert_eq!(edit.remove, 0);
            e.apply(edit);
        }
        assert_eq!(e.text, "tieengs");
        let edit = e.s.snapshot(&e.text, 7, 7);
        e.apply(edit);
        assert_eq!(e.text, "tiếng");
    }
    #[test]
    fn late_snapshot_composes_owned_burst_across_word_boundaries() {
        let mut e = Editor::new();
        e.s.snapshot("", 0, 0);
        for key in "tieengs vieetj ".chars() {
            let edit = e.s.key(key);
            e.apply(edit);
        }
        assert_eq!(e.text, "tieengs vieetj ");
        let n = e.text.chars().count();
        let edit = e.s.snapshot(&e.text, n, n);
        e.apply(edit);
        assert_eq!(e.text, "tiếng việt ");
    }
    #[test]
    fn password_pin_terminal_and_private_hints_pass_through() {
        for (p, h) in [(8, 0), (9, 0), (10, 0), (0, 1 << 11), (0, 1 << 12)] {
            let mut e = Editor::new();
            e.key('a');
            e.s.content(p, h);
            assert_eq!(e.s.key('s'), Edit::default());
            assert_eq!(e.s.snapshot("as", 2, 2), Edit::default());
        }
    }
    #[test]
    fn unknown_purpose_is_closed_and_missing_capability_is_native() {
        let mut s = Session::new(ToneStyle::Modern, true, 256, true);
        s.capabilities(32);
        assert!(!s.key('a').handled);
        s.content(0, 0);
        s.capabilities(1);
        assert!(!s.key('a').handled);
    }
    #[test]
    fn explicit_unknown_purpose_is_protected_not_inferred_public() {
        let mut e = Editor::new();
        e.key('a');
        for purpose in [11, 99, u32::MAX] {
            e.s.content(purpose, 0);
            assert!(e.s.protected(), "unknown purpose must be closed");
            assert!(!e.s.key('s').handled);
            assert_eq!(e.s.snapshot("as", 2, 2), Edit::default());
        }
        e.s.content(0, 0);
        assert!(e.s.key('a').handled);
    }
    #[test]
    fn foreign_caret_and_selections_never_delete() {
        for (doc, cursor, anchor) in [("ba", 2, 2), ("a", 0, 0), ("a", 1, 0), ("🙂", 1, 1)] {
            let mut e = Editor::new();
            e.key('a');
            e.s.snapshot(doc, cursor, anchor);
            assert_eq!(e.s.key('s').remove, 0);
        }
    }
    #[test]
    fn invalid_snapshot_clears_composition() {
        let mut e = Editor::new();
        e.key('a');
        e.s.snapshot("", 100, 100);
        assert_eq!(e.s.key('s').remove, 0);
    }
    #[test]
    fn freeze_escape_and_native_backspace_preserve_visible_word() {
        let mut e = Editor::new();
        e.key('u');
        e.s.freeze();
        e.key('s');
        assert_eq!(e.text, "us");
        e.key(' ');
        for k in "tieengs".chars() {
            e.key(k);
        }
        let n = e.text.chars().count();
        let ack = e.s.snapshot(&e.text, n, n);
        e.apply(ack);
        let edit = e.s.escape();
        e.apply(edit);
        assert_eq!(e.text, "us tieengs");
        let mut e = Editor::new();
        for k in "dduwowngf".chars() {
            e.key(k);
        }
        e.text.pop();
        e.s.backspace();
        e.key('g');
        assert_eq!(e.text, "đường");
    }
    #[test]
    fn focus_reset_cannot_recommit_the_previous_word() {
        let mut e = Editor::new();
        for k in "aas".chars() {
            e.key(k);
        }
        e.s.reset();
        e.text = "other ".into();
        e.key('a');
        e.key('s');
        assert_eq!(e.text, "other á");
    }
    #[test]
    fn departed_context_cannot_lend_its_public_purpose_to_an_unknown_field() {
        let mut e = Editor::new();
        e.key('a');
        e.s.leave_context();
        assert!(!e.s.key('s').handled);
        e.s.content(0, 0);
        assert!(e.s.key('s').handled);
    }
    #[test]
    fn client_reset_after_every_commit_keeps_the_word_composable() {
        // Measured behaviour of Firefox's GTK IM context (19/11): after each key it
        // applies the edit, calls Reset on the engine, then republishes the text.
        // A reset must not throw away a word the surrounding text still proves.
        let mut s = Session::new(ToneStyle::Modern, true, 256, true);
        s.capabilities(32);
        s.content(0, 0);
        let mut text = String::new();
        for key in "tieengs".chars() {
            let n = text.chars().count();
            let ack = s.snapshot(&text, n, n);
            for _ in 0..ack.remove {
                text.pop();
            }
            text.push_str(&ack.insert);
            let edit = s.key(key);
            for _ in 0..edit.remove {
                text.pop();
            }
            text.push_str(&edit.insert);
            s.client_reset();
            let n = text.chars().count();
            let ack = s.snapshot(&text, n, n);
            for _ in 0..ack.remove {
                text.pop();
            }
            text.push_str(&ack.insert);
        }
        assert_eq!(text, "tiếng");
    }
    #[test]
    fn client_reset_without_matching_surrounding_starts_a_new_word() {
        let mut e = Editor::new();
        for k in "aas".chars() {
            e.key(k);
        }
        e.s.client_reset();
        e.text = "other ".into();
        e.s.snapshot(&e.text, 6, 6);
        e.key('a');
        e.key('s');
        assert_eq!(e.text, "other á");
    }
    #[test]
    fn gtk_reset_after_native_backspace_requires_exact_app_confirmation() {
        let mut e = Editor::new();
        for k in "tieengs".chars() {
            e.key(k);
        }
        let n = e.text.chars().count();
        e.s.snapshot(&e.text, n, n);
        e.s.backspace();
        e.text.pop();
        e.s.client_reset();
        let n = e.text.chars().count();
        e.s.snapshot(&e.text, n, n);
        e.key('f');
        assert_eq!(e.text, "tiền");
    }
    #[test]
    fn backspace_ticket_never_survives_focus_or_a_different_caret() {
        for leave in [false, true] {
            let mut e = Editor::new();
            for k in "tieengs".chars() {
                e.key(k);
            }
            let n = e.text.chars().count();
            e.s.snapshot(&e.text, n, n);
            e.s.backspace();
            e.s.client_reset();
            if leave {
                e.s.leave_context();
                e.s.content(0, 0);
            }
            e.s.snapshot("foreign tiến", 12, 12);
            assert_eq!(e.s.key('f').remove, 0);
        }
    }
    #[test]
    fn ctrl_freeze_reanchors_escape_at_the_visible_composed_text() {
        let mut e = Editor::new();
        e.key('a');
        e.key('a');
        e.s.freeze();
        e.key('s');
        assert_eq!(e.text, "âs");
        let n = e.text.chars().count();
        e.s.snapshot(&e.text, n, n);
        let edit = e.s.escape();
        e.apply(edit);
        assert_eq!(e.text, "âs");
    }
    #[test]
    fn word_limit_keeps_remaining_keys_literal_until_boundary() {
        let mut e = Editor::new();
        e.s.max_keys = 8;
        for k in "bbbbbbbbaas".chars() {
            e.key(k);
        }
        assert_eq!(e.text, "bbbbbbbbaas");
        e.key(' ');
        e.key('a');
        e.key('s');
        assert_eq!(e.text, "bbbbbbbbaas á");
    }
}
