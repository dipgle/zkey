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
    /// Purpose TERMINAL (10). Bypassed unless the client ALSO reports surrounding text:
    /// measured 21/11 — GNOME Text Editor (GTK4) declares TERMINAL while sending
    /// surrounding text, and the old rule left the user unable to type Vietnamese there.
    terminal: bool,
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
    /// (text, caret) of the word most recently committed before a separator;
    /// used only to adopt that word back when the separator is deleted.
    committed: Option<(String, usize)>,
    /// Word frozen by Ctrl/Escape: later mark keys must append, never rewrite it.
    frozen: Option<String>,
    /// The client published surrounding text at least once in this focus session:
    /// it has shown us the field it types into.
    published: bool,
    /// The client republished text AFTER one of our commits/resets. Such a client
    /// watches the field, so its silence is never taken as permission to guess.
    reports_caret: bool,
    /// Continuing a word whose only copy is our own buffer. Measured 20/11: the
    /// Files search entry publishes one empty snapshot at focus, then resets after
    /// every commit and never sends another snapshot, so `owns()` can never be
    /// proven again and the whole word would collapse into per-key inserts.
    blind: bool,
    /// Content type the client last announced (purpose, hints).
    content_type: Option<(u32, u32)>,
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
            terminal: false,
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
            committed: None,
            frozen: None,
            published: false,
            reports_caret: false,
            blind: false,
            content_type: None,
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
        self.blind = false;
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
        self.committed = None;
        self.frozen = None;
        self.published = false;
        self.reports_caret = false;
        self.protected = true;
    }
    pub fn configure(&mut self, config: &crate::config::Config, experimental: bool) {
        self.style = config.style;
        self.enabled = config.enabled;
        self.max_keys = config.max_word_keys;
        self.rewrite_allowed = experimental || config.experimental_rewrite;
        self.reset();
        self.committed = None;
    }
    pub fn capabilities(&mut self, caps: u32) {
        self.capable = caps & (1 << 5) != 0;
        self.committed = None;
        if !self.capable {
            self.reset();
        }
    }
    pub fn content(&mut self, purpose: u32, hints: u32) {
        // Public IBus purposes 0..7 are non-secret. PASSWORD/PIN/TERMINAL and
        // any future/unknown purpose stay closed until explicitly supported.
        // Purposes: 8 PASSWORD, 9 PIN, 10 TERMINAL, 11.. unknown. Terminal is decided in
        // accepts(): it only bypasses while the client gives no surrounding text.
        let changed = self.content_type != Some((purpose, hints));
        self.content_type = Some((purpose, hints));
        self.terminal = purpose == 10;
        self.protected =
            (!matches!(purpose, 0..=7) && purpose != 10) || hints & ((1 << 11) | (1 << 12)) != 0;
        self.committed = None;
        if self.protected || changed {
            // A different field may sit at a different caret: never carry a word
            // (or an unconfirmed buffer) across a content-type change.
            self.reset();
        }
    }
    pub fn protected(&self) -> bool {
        self.protected
    }
    /// Contexts where text may be tracked at all (no password/PIN/unknown purpose).
    fn tracks(&self) -> bool {
        self.enabled && self.capable && !self.protected && self.rewrite_allowed
    }
    /// Keys are composed only when the client also proves it can be edited (surrounding
    /// text) in a TERMINAL context; otherwise the engine keeps its hands off.
    pub fn accepts(&self) -> bool {
        self.tracks() && (!self.terminal || self.snapshot.is_some())
    }
    pub fn snapshot(&mut self, text: &str, cursor: usize, anchor: usize) -> Edit {
        // Tracking is required even for a TERMINAL context that turns out to send
        // surrounding text (GNOME Text Editor): accepts() then needs that snapshot.
        if !self.tracks() {
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
        self.published = true;
        // A snapshot that arrives after a commit/reset and lands on text we are
        // composing is proof this client watches the caret. Such a client is never
        // composed for blindly again in this focus session.
        if (self.reset_pending || self.blind)
            && (!self.visible.is_empty() || self.pending.is_some())
        {
            self.reports_caret = true;
        }
        if self.blind {
            // The buffer was a guess. Now the client showed the field: keep the
            // word only if it is still exactly there, otherwise drop it untouched.
            self.blind = false;
            if !self.owns() {
                self.reset();
                return Edit::default();
            }
        }
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
    /// Whether a client Reset may be answered by continuing our own word. Only for
    /// a context that has already shown us its field (`published`) but has never
    /// republished it after a commit (`reports_caret`): the measured Files search
    /// entry. The buffer must be a word we composed ourselves, still identical to
    /// what we committed, with no pending span and no Ctrl/Escape freeze.
    fn blind_continuation_allowed(&self) -> bool {
        self.published
            && !self.reports_caret
            && !self.literal
            && self.pending.is_none()
            && !self.visible.is_empty()
            && self.word.text() == self.visible
    }
    /// Adopt the syllable we just committed when the client deleted the
    /// separator with a native Backspace: the caret is still exactly where that
    /// word ends, and the text still ends with it. Nothing else is adopted, so a
    /// foreign caret can never make us delete someone else's text.
    fn seed_from_surrounding(&mut self) -> bool {
        let Some((text, caret)) = self.committed.take() else {
            return false;
        };
        let Some(s) = &self.snapshot else {
            return false;
        };
        let word: Vec<char> = text.chars().collect();
        if !s.selection
            && s.cursor == caret
            && word.len() <= s.before.len()
            && s.before[s.before.len() - word.len()..] == word[..]
            && word.len() < self.max_keys
            && let Ok(seeded) = Composer::seed(self.style, &text)
        {
            self.word = seeded;
            self.visible = text;
            self.origin = Some(caret - word.len());
            return true;
        }
        false
    }
    /// A mark key whose caret sits right after a word that is on screen but was NOT typed in
    /// this composition (pasted text, an earlier session, another app). Hà 21/11: «cứ con trỏ
    /// đứng cuối từ là gõ dấu vẫn nhận». Adopted only when the key actually CHANGES the word
    /// (a mark), never to glue a plain letter onto it, never with a selection, never across a
    /// non-letter boundary, never for a word at/over max_keys. Contexts that must stay literal
    /// (terminal, password, protected, Ctrl-frozen words) never reach here.
    fn mark_finishes_document_word(&mut self, key: char) -> Option<Edit> {
        // Tone marks only (s f r x j z). 'a'/'w' are Telex modifiers too, but applying them
        // to text the user did not type would rewrite words nobody asked to compose.
        if !matches!(
            key,
            's' | 'f' | 'r' | 'x' | 'j' | 'z' | 'S' | 'F' | 'R' | 'X' | 'J' | 'Z'
        ) {
            return None;
        }
        let (word, caret) = {
            let s = self.snapshot.as_ref()?;
            if s.selection {
                return None;
            }
            let mut start = s.before.len();
            while start > 0 && s.before[start - 1].is_alphabetic() {
                start -= 1;
            }
            let word: String = s.before[start..].iter().collect();
            if word.is_empty() || word.chars().count() >= self.max_keys {
                return None;
            }
            if self
                .frozen
                .as_ref()
                .is_some_and(|frozen| !frozen.is_empty() && word.starts_with(frozen.as_str()))
            {
                return None; // Ctrl/Escape froze this word: later keys append, never rewrite
            }
            (word, s.cursor)
        };
        let mut composer = Composer::seed(self.style, &word).ok()?;
        if composer.push(key).is_err() {
            return None;
        }
        let wanted = composer.text();
        if wanted.chars().count() > word.chars().count() {
            return None; // the key would only add a character: a new word, not a mark
        }
        let common = word
            .chars()
            .zip(wanted.chars())
            .take_while(|(a, b)| a == b)
            .count();
        self.word = composer;
        self.visible = wanted.clone();
        self.origin = Some(caret - word.chars().count());
        self.snapshot = None;
        Some(Edit {
            handled: true,
            remove: (word.chars().count() - common) as u32,
            insert: wanted.chars().skip(common).collect(),
        })
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
        self.frozen = Some(self.visible.clone());
    }
    pub fn key(&mut self, key: char) -> Edit {
        self.native_backspace = None;
        if !self.accepts() {
            self.reset();
            self.committed = None;
            return Edit::default();
        }
        if self.reset_pending {
            // A Reset means the client dropped its IM state, not that the field is
            // empty. Keep our word only for a client that has shown us the field but
            // never republishes it (the snapshot that follows a Reset must prove the
            // word otherwise); everything else starts a new word here.
            if self.blind_continuation_allowed() {
                self.reset_pending = false;
                self.blind = true;
                self.origin = None; // The caret is unverified now; no origin claim.
            } else {
                self.reset();
            }
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
            let mut committed = None;
            let word = match &self.pending {
                Some(previous) => format!("{}{wanted}", previous.wanted),
                None => wanted.clone(),
            };
            let start = self.pending.as_ref().and_then(|p| p.origin).or(self.origin);
            if !self.literal
                && let Some(origin) = start
            {
                // Remember the word we just committed and where an app that
                // deleted the separator would leave the caret, so a later mark
                // key can finish it instead of starting a new word.
                committed = Some((word.clone(), origin + word.chars().count()));
            }
            let pending = if self.pending.is_some() || wanted != self.visible {
                let previous = self.pending.take().unwrap_or(PendingSpan {
                    visible: String::new(),
                    wanted: String::new(),
                    origin: self.origin,
                });
                let visible = format!("{}{}{key}", previous.visible, self.visible);
                let wanted = format!("{}{key}", word);
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
            self.committed = committed;
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
        let owned = self.owns() || self.blind;
        if self.visible.is_empty() && !self.seed_from_surrounding() {
            if let Some(edit) = self.mark_finishes_document_word(key) {
                return edit;
            }
            self.origin = self
                .snapshot
                .as_ref()
                .filter(|s| !s.selection)
                .map(|s| s.cursor);
        }
        let owned = owned || self.owns() || self.blind;
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
        if self.visible.is_empty() {
            self.blind = false;
        }
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
    fn terminal_bypasses_only_without_surrounding_text() {
        // VTE/readline: purpose TERMINAL, no surrounding text -> engine keeps hands off
        // (handled=false, the app inserts the key itself).
        let mut s = Session::new(ToneStyle::Modern, true, 256, true);
        s.capabilities(32);
        s.content(10, 0);
        assert!(!s.key('a').handled);
        assert!(!s.key('s').handled);
        // GNOME Text Editor (measured 21/11): TERMINAL + surrounding text -> compose.
        let mut e = Editor::new();
        e.s.content(10, 0);
        for k in "tieengs".chars() {
            e.key(k);
        }
        assert_eq!(e.text, "tiếng");
        // Password/PIN stay closed no matter what surrounding text arrives.
        let mut s = Session::new(ToneStyle::Modern, true, 256, true);
        s.capabilities(32);
        s.content(8, 0);
        s.snapshot("pass", 4, 4);
        assert!(!s.key('a').handled);
        assert!(!s.key('s').handled);
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
    fn apply_edit(text: &mut String, edit: &Edit) -> u32 {
        for _ in 0..edit.remove {
            text.pop();
        }
        text.push_str(&edit.insert);
        edit.remove
    }
    /// Measured 20/11 (Files search entry): the context publishes ONE empty snapshot
    /// when it is created, then calls Reset after every commit and never sends
    /// surrounding text again. Our own buffer is then the only copy of the word.
    fn silent_client() -> (Session, String) {
        let mut s = Session::new(ToneStyle::Modern, true, 256, true);
        s.capabilities(32);
        s.content(0, 0);
        s.snapshot("", 0, 0);
        (s, String::new())
    }
    fn silent_keys(s: &mut Session, text: &mut String, keys: &str) -> u32 {
        let mut removes = 0;
        for key in keys.chars() {
            let edit = s.key(key);
            removes += apply_edit(text, &edit);
            s.client_reset();
        }
        removes
    }
    #[test]
    fn client_that_never_republishes_after_reset_still_composes() {
        let (mut s, mut text) = silent_client();
        let removes = silent_keys(&mut s, &mut text, "tieengs");
        assert_eq!(text, "tiếng");
        assert!(removes > 0, "a composed word needs at least one rewrite");
    }
    #[test]
    fn first_word_mark_lands_without_any_caret_report() {
        // The screenshot case from Telegram web: "mowis" must become "mới" in a
        // context that never confirms the caret.
        let (mut s, mut text) = silent_client();
        silent_keys(&mut s, &mut text, "mowis");
        assert_eq!(text, "mới");
    }
    #[test]
    fn silent_contexts_keep_composing_after_a_separator() {
        let (mut s, mut text) = silent_client();
        silent_keys(&mut s, &mut text, "tieengs vieetj");
        assert_eq!(text, "tiếng việt");
    }
    #[test]
    fn a_context_that_never_published_text_is_never_guessed_at() {
        // No snapshot at all: the client never showed us the field, so every key
        // stays a literal insert (this is the reverse control for the buffer).
        let mut s = Session::new(ToneStyle::Modern, true, 256, true);
        s.capabilities(32);
        s.content(0, 0);
        let mut text = String::new();
        let mut removes = 0;
        for key in "tieengs".chars() {
            removes += apply_edit(&mut text, &s.key(key));
            s.client_reset();
        }
        assert_eq!(text, "tieengs");
        assert_eq!(removes, 0);
    }
    #[test]
    fn a_contradicting_snapshot_drops_the_unconfirmed_word() {
        let (mut s, mut text) = silent_client();
        silent_keys(&mut s, &mut text, "tie");
        assert_eq!(
            s.snapshot("xyz", 3, 3),
            Edit::default(),
            "a snapshot that does not end with our word must not be edited"
        );
        text = "xyz".into();
        let edit = s.key('n');
        assert_eq!((edit.remove, edit.insert.as_str()), (0, "n"));
        apply_edit(&mut text, &edit);
        assert_eq!(text, "xyzn");
    }
    #[test]
    fn leaving_the_context_drops_the_unconfirmed_word() {
        let (mut s, mut text) = silent_client();
        silent_keys(&mut s, &mut text, "tie");
        s.leave_context();
        s.content(0, 0);
        let edit = s.key('n');
        assert_eq!((edit.remove, edit.insert.as_str()), (0, "n"));
    }
    #[test]
    fn native_backspace_inside_an_unconfirmed_word_keeps_the_rest_composable() {
        let (mut s, mut text) = silent_client();
        silent_keys(&mut s, &mut text, "sawc");
        assert_eq!(text, "săc");
        s.backspace();
        text.pop();
        assert_eq!(text, "să");
        let edit = s.key('s');
        apply_edit(&mut text, &edit);
        s.client_reset();
        assert_eq!(text, "sắ");
        let edit = s.key('c');
        apply_edit(&mut text, &edit);
        s.client_reset();
        assert_eq!(text, "sắc");
    }
    #[test]
    fn a_terminal_that_stops_confirming_is_left_alone() {
        // TERMINAL composes only while a snapshot proves the field. The silent
        // buffer must never keep a terminal open (VTE/readline give no snapshot).
        let mut s = Session::new(ToneStyle::Modern, true, 256, true);
        s.capabilities(32);
        s.content(10, 0);
        s.snapshot("", 0, 0);
        assert!(s.key('t').handled);
        s.client_reset();
        assert!(
            !s.key('i').handled,
            "no snapshot => terminal stays bypassed"
        );
    }
    #[test]
    fn a_selection_never_lets_the_silent_buffer_rewrite() {
        let (mut s, mut text) = silent_client();
        silent_keys(&mut s, &mut text, "ti");
        // A selection is not a caret we may edit around.
        assert_eq!(s.snapshot("ti", 2, 0), Edit::default());
        let edit = s.key('e');
        assert_eq!(
            edit.remove, 0,
            "selection => never delete what we did not see"
        );
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
    fn document_word_gets_the_mark_without_reviving_an_old_composition() {
        // Hà 21/11: a mark at the caret finishes the word that is THERE. An old
        // backspace ticket must not make the engine delete the whole previous word,
        // and focus change must not smuggle the old composition in either.
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
            let edit = e.s.key('f');
            assert_eq!((edit.remove, edit.insert.as_str()), (2, "ền"));
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
    fn deleted_separator_lets_a_mark_finish_the_previous_syllable() {
        // Hà 20/11: "săc" + space, delete the space with native Backspace, then
        // "s" must give "sắc" — the syllable already on screen is still mine.
        let mut e = Editor::new();
        for k in "sawc".chars() {
            e.key(k);
        }
        assert_eq!(e.text, "săc");
        e.key(' ');
        assert_eq!(e.text, "săc ");
        let n = e.text.chars().count();
        e.s.snapshot(&e.text, n, n);
        e.s.backspace();
        e.text.pop();
        e.key('s');
        assert_eq!(e.text, "sắc");
    }
    #[test]
    fn mark_finishes_a_word_that_was_already_on_screen() {
        // Hà 21/11: a word on screen that this engine never typed (pasted, earlier
        // session) still gets the mark when the caret is at its end.
        let mut e = Editor::new();
        e.text = "lạ".into();
        e.s.snapshot(&e.text, 2, 2);
        let edit = e.s.key('s');
        assert_eq!((edit.remove, edit.insert.as_str()), (1, "á"));
        e.apply(edit);
        assert_eq!(e.text, "lá");
    }
    #[test]
    fn plain_letter_after_a_document_word_is_appended_not_adopted() {
        // Adoption is for marks only: a plain letter must not glue to the old word.
        let mut e = Editor::new();
        e.text = "lạ".into();
        e.s.snapshot(&e.text, 2, 2);
        let edit = e.s.key('a');
        assert_eq!(edit.remove, 0);
        e.apply(edit);
        assert_eq!(e.text, "lạa");
    }
    #[test]
    fn document_word_is_not_adopted_with_a_selection_or_across_a_boundary() {
        let mut e = Editor::new();
        e.text = "lạ".into();
        e.s.snapshot(&e.text, 2, 0);
        assert_eq!(e.s.key('s').remove, 0);
        let mut e = Editor::new();
        e.text = "lạ1".into();
        e.s.snapshot(&e.text, 3, 3);
        let edit = e.s.key('s');
        e.apply(edit);
        assert_eq!(e.text, "lạ1s");
        // A letter run right before the caret is adopted even after a digit boundary.
        let mut e = Editor::new();
        e.text = "1lạ".into();
        e.s.snapshot(&e.text, 3, 3);
        let edit = e.s.key('s');
        assert_eq!((edit.remove, edit.insert.as_str()), (1, "á"));
        e.apply(edit);
        assert_eq!(e.text, "1lá");
        // The word before the caret is only the one inside a letter run: here "ạ".
        let mut e = Editor::new();
        e.text = "a lạ".into();
        e.s.snapshot(&e.text, 4, 4);
        let edit = e.s.key('s');
        assert_eq!((edit.remove, edit.insert.as_str()), (1, "á"));
        e.apply(edit);
        assert_eq!(e.text, "a lá");
    }
    #[test]
    fn document_word_is_not_adopted_beyond_max_keys() {
        let mut e = Editor::new();
        e.s.max_keys = 8;
        e.text = "nghieeng".into();
        e.s.snapshot(&e.text, 8, 8);
        assert_eq!(e.s.key('s').remove, 0);
    }
    #[test]
    fn literal_words_are_not_adopted_after_a_deleted_separator() {
        // Ctrl/Escape froze "u" as typed: the next mark key appends, never edits.
        let mut e = Editor::new();
        e.key('u');
        e.s.freeze();
        e.key('s');
        assert_eq!(e.text, "us");
        e.key(' ');
        assert_eq!(e.text, "us ");
        e.text.pop();
        e.key('s');
        assert_eq!(e.text, "uss");
    }
    #[test]
    fn seed_requires_the_recorded_caret_and_no_selection() {
        let mut e = Editor::new();
        for k in "sawc ".chars() {
            e.key(k);
        }
        e.text.pop();
        e.s.snapshot(&e.text, 3, 0);
        assert_eq!(e.s.key('s').remove, 0);
        let mut e = Editor::new();
        e.s.max_keys = 8;
        for k in "khonggch ".chars() {
            e.key(k);
        }
        assert_eq!(e.text, "khonggch ");
        e.text.pop();
        let n = e.text.chars().count();
        e.s.snapshot(&e.text, n, n);
        assert_eq!(
            e.s.key('s').remove,
            0,
            "a word at the key limit is not adopted"
        );
    }
    #[test]
    fn seed_stops_at_a_separator_and_document_start() {
        let mut e = Editor::new();
        e.text = "săc ".into();
        e.s.snapshot(&e.text, 4, 4);
        assert_eq!(e.s.key('s').remove, 0);
        // Our own word at the very start of the field is still ours.
        let mut e = Editor::new();
        for k in "aw ".chars() {
            e.key(k);
        }
        assert_eq!(e.text, "ă ");
        e.text.pop();
        e.key('s');
        assert_eq!(e.text, "ắ");
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
