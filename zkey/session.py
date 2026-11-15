"""Telex over text already received by the application; never holds a preedit.

Only rewrite text we committed ourselves, and only when a client-provided
surrounding snapshot shows exactly that text right before the caret with no
selection. Unsupported clients get native keys.

Ordering contract (measured 15/11 on GTK3 burst, "tieengs" -> "tieseng"):
async IBus clients re-queue keys an engine does not handle behind text it
commits for later keys. In a supported context every printable key is
therefore committed by us; only non-printable keys go native. Keys that
arrive before the app confirms our last commit are committed as typed; the
next confirming snapshot (a later key or the app's own update) composes them.
"""
from dataclasses import dataclass
from .config import Config

PENDING_WORDS = 3  # Earlier words kept for a late confirmation (bounded rewrite).
PENDING_CHARS = 64


@dataclass(frozen=True)
class Result:
    handled: bool = False
    preedit: str | None = None  # Used only to cancel an old client preedit.
    commit: str | None = None
    delete: int = 0  # Unicode code points immediately before the caret.


class Session:
    def __init__(self, core, config=None):
        self.core = core
        self.config = config or Config()
        self.private = False
        self.surrounding_supported = False
        self.clear()

    def clear(self):
        self.previous = []  # [raw, text, separator, dirty] committed before the current word
        self.new_word()

    def new_word(self):
        self.raw = ""
        self.text = ""
        self.literal = False
        self.bypass_word = False
        self.dirty = False  # Keys committed as typed after the first, not yet composed.

    def flush(self):
        # Everything was committed per key; lifecycle changes must not repeat it.
        self.clear()
        return Result()

    def span(self):
        return "".join(text + separator for _raw, text, separator, _dirty in self.previous) + self.text

    def owns(self, surrounding):
        """The app's own snapshot shows exactly our committed span before the caret.

        Position-free on purpose: after a reset the word start is unknown.
        A snapshot older than our last commit can only end with our full span
        if the character before it is a letter (repeated-letter case), so the
        span must start at a non-letter or the start of the text.
        """
        span = self.span()
        if surrounding is None or not span:
            return False
        document, cursor, anchor = surrounding
        start = cursor - len(span)
        if cursor != anchor or start < 0 or cursor > len(document) or document[start:cursor] != span:
            return False
        return start == 0 or not document[start - 1].isalpha()

    def target(self, raw, text, literal=False):
        if literal:
            return raw
        if not raw.isascii():
            # Edited by Backspace: raw is already the app's composed text. Final.
            return text
        return self.core.compose(raw, self.config.modern_tone)  # errors reach the engine log

    def rewrite(self, raw, text):
        """Replace our confirmed span: earlier words composed, current word = text."""
        old = self.span()
        self.previous = [[r, self.target(r, t) if d else t, s, False] for r, t, s, d in self.previous]
        self.raw, self.text, self.dirty = raw, text, False
        new = self.span()
        self.previous = []  # All composed and confirmed: nothing left pending.
        common = 0
        while common < min(len(old), len(new)) and old[common] == new[common]:
            common += 1
        return Result(True, commit=new[common:] or None, delete=len(old) - common)

    def pending(self):
        return self.dirty or any(dirty for _raw, _text, _separator, dirty in self.previous)

    def append(self, key):
        """Commit one key as typed, with no deletion; keeps our span model exact."""
        self.dirty = self.dirty or bool(self.raw)
        self.raw += key
        self.text += key
        return Result(True, commit=key)

    def catch_up(self, surrounding):
        """Compose keys committed unconfirmed, once the app's own update shows them.

        Called on an incoming client update only. The engine is sequential, so
        this rewrite is emitted before its reply to any later native key.
        """
        if (self.private or not self.surrounding_supported or not self.config.enabled
                or self.bypass_word or not self.pending() or not self.owns(surrounding)):
            return Result()
        result = self.rewrite(self.raw, self.target(self.raw, self.text, self.literal))
        return result if result.delete or result.commit else Result()

    def boundary(self, key):
        """Commit a separator ourselves (ordering); keep unconfirmed words pending."""
        if self.raw and self.pending():
            self.previous.append([self.raw, self.text, key, self.dirty])
        elif not self.raw and self.previous:
            self.previous[-1][2] += key
        else:
            self.previous = []
        while self.previous and (len(self.previous) > PENDING_WORDS or len(self.span()) > PENDING_CHARS):
            self.previous.pop(0)  # Oldest stays as typed; never rewritten.
        self.new_word()
        return Result(True, commit=key)

    def key(self, key, *, surrounding=None, shortcut=False, release=False):
        if release:
            return Result()
        if self.private or not self.surrounding_supported or not self.config.enabled or shortcut:
            return self.flush()
        if surrounding is not None:
            document, cursor, anchor = surrounding
            if not 0 <= cursor <= len(document) or cursor != anchor:
                # The app replaces a selection natively; nothing of ours is safe to extend.
                return self.flush()
        printable = len(key) == 1 and key.isprintable()
        letter = printable and key.isascii() and key.isalpha()
        if key == "BackSpace":
            # Let the app do its native deletion; track only our remaining text.
            if self.raw:
                self.raw = self.text = self.text[:-1]
                if not self.text:
                    self.new_word()
            else:
                self.clear()
            return Result()
        if key == "Escape" and self.raw:
            if not self.owns(surrounding):
                return self.flush()
            result = self.rewrite(self.raw, self.raw)
            self.literal = True
            return result
        if not printable:
            return self.flush()
        if not letter:
            return self.boundary(key)
        if self.bypass_word:
            return Result(True, commit=key)
        if len(self.raw) >= self.config.max_word_keys:
            self.clear()
            self.bypass_word = True
            return Result(True, commit=key)
        if not self.owns(surrounding):
            # First letter, or unconfirmed (awaiting the app's update, or a
            # stale/foreign snapshot): never rewrite. Extend our exact model;
            # a later matching snapshot composes it.
            return self.append(key)
        raw = self.raw + key
        return self.rewrite(raw, self.target(raw, self.text + key, self.literal))
