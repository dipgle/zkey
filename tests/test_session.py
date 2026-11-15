"""Committed-text contracts against an editor model, not UI acceptance."""
import unittest
from zkey.config import Config
from zkey.core import Core
from zkey.session import Session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.session = Session(Core())
        self.session.surrounding_supported = True
        self.document = ""
        self.cursor = self.anchor = 0

    def key(self, key, **kwargs):
        result = self.session.key(key, surrounding=(self.document, self.cursor, self.anchor), **kwargs)
        if result.delete:
            self.document = self.document[:self.cursor-result.delete] + self.document[self.cursor:]
            self.cursor -= result.delete
        if result.commit:
            self.document = self.document[:self.cursor] + result.commit + self.document[self.cursor:]
            self.cursor += len(result.commit)
        if not result.handled and not kwargs.get("release") and not kwargs.get("shortcut"):
            if key == "BackSpace" and self.cursor:
                self.document = self.document[:self.cursor-1] + self.document[self.cursor:]
                self.cursor -= 1
            elif len(key) == 1:
                self.document = self.document[:self.cursor] + key + self.document[self.cursor:]
                self.cursor += len(key)
        self.anchor = self.cursor
        return result

    def type(self, raw):
        return [self.key(key) for key in raw]

    def test_word_then_boundary_commits_exactly_once(self):
        expected = ("t", "ti", "tie", "tiê", "tiên", "tiêng", "tiếng")
        self.assertEqual(len(expected), len("tieengs"))
        for key, text in zip("tieengs", expected):
            result = self.key(key)
            self.assertTrue(result.handled)
            self.assertIsNone(result.preedit)
            self.assertEqual(self.document, text)
        self.assertEqual(self.key(" ").commit, " ")
        self.assertEqual(self.document, "tiếng ")
        self.assertIsNone(self.key("Return").commit)

    def test_backspace_deletes_visible_letter_and_keeps_tone(self):
        self.type("dduwowngf")
        self.assertEqual(self.document, "đường")
        self.assertFalse(self.key("BackSpace").handled)
        self.assertEqual(self.document, "đườn")
        self.key("BackSpace")
        self.assertEqual(self.document, "đườ")
        self.type("ng")
        self.assertEqual(self.document, "đường")

    def test_escape_restores_original_keystrokes(self):
        self.type("tieengs")
        self.assertTrue(self.key("Escape").handled)
        self.assertEqual(self.document, "tieengs")
        self.type("s ")
        self.assertEqual(self.document, "tieengss ")

    def test_shortcut_does_not_recommit_received_text(self):
        self.type("Vieetj")
        result = self.key("a", shortcut=True)
        self.assertFalse(result.handled)
        self.assertIsNone(result.commit)
        self.assertEqual(self.document, "Việt")

    def test_release_does_not_duplicate(self):
        self.type("a")
        self.assertFalse(self.key("a", release=True).handled)
        self.assertEqual(self.document, "a")

    def test_password_drops_buffers_and_passes_through(self):
        self.type("as")
        self.session.private = True
        for key in "as":
            result = self.key(key)
            self.assertFalse(result.handled)
            self.assertIsNone(result.commit)
            self.assertEqual(result.delete, 0)
        self.assertEqual(self.document, "áas")
        self.assertEqual(self.session.raw, "")
        self.session.clear()
        self.assertTrue(self.session.private)

    def test_no_surrounding_support_passes_through(self):
        self.session.surrounding_supported = False
        self.type("as")
        self.assertEqual(self.document, "as")
        self.assertEqual(self.session.raw, "")

    def test_disabled_passes_through(self):
        self.session.config = Config(enabled=False)
        self.assertFalse(self.key("a").handled)

    def test_focus_reset_prevents_cross_context_text(self):
        self.type("tieengs")
        self.session.clear()
        self.document = "other "
        self.cursor = self.anchor = len(self.document)
        self.type("as")
        self.assertEqual(self.document, "other á")

    def test_long_token_passes_through_to_boundary(self):
        self.session.config = Config(max_word_keys=8)
        self.type("bbbbbbbb")
        self.assertEqual(self.key("a").commit, "a")
        self.assertEqual(self.key("s").commit, "s")
        self.assertEqual(self.document, "bbbbbbbbas")
        self.key(" ")
        self.assertTrue(self.key("a").handled)

    def test_native_ffi_rejects_invalid_input(self):
        for raw in ("a!", "a" * 257, "🙂"):
            with self.assertRaises(ValueError):
                self.session.core.compose(raw)

    def test_configs_change_tone_placement(self):
        self.session.config = Config(modern_tone=False)
        self.type("hoaf")
        self.assertEqual(self.document, "hòa")
        self.session.clear()
        self.document = ""
        self.cursor = self.anchor = 0
        self.session.config = Config(modern_tone=True)
        self.type("hoaf")
        self.assertEqual(self.document, "hoà")

    def test_foreign_edit_caret_or_selection_never_rewrites_old_word(self):
        for document, cursor, anchor in (("a!", 2, 2), ("a", 0, 0), ("a", 1, 0), ("x", 1, 1)):
            with self.subTest(document=document, cursor=cursor, anchor=anchor):
                self.setUp()
                self.type("a")
                result = self.session.key("s", surrounding=(document, cursor, anchor))
                self.assertEqual(result.delete, 0)
                self.assertNotEqual(result.commit, "á")

    def test_missing_or_stale_client_update_does_not_delete_text(self):
        self.type("a")
        result = self.session.key("s", surrounding=("", 0, 0))
        self.assertEqual(result.delete, 0)
        self.assertNotEqual(result.commit, "á")
        self.session.clear()
        result = self.session.key("a", surrounding=None)
        self.assertEqual((result.handled, result.commit, result.delete), (True, "a", 0))

    def test_unconfirmed_keys_are_committed_in_order_never_passed_native(self):
        # Native pass-through is re-queued by async IBus clients behind later
        # commits (GTK3 burst measured 15/11: "tieengs" -> "tieseng").
        self.type("a")
        result = self.session.key("a", surrounding=None)
        self.assertTrue(result.handled)
        self.assertEqual((result.commit, result.delete), ("a", 0))
        self.document, self.cursor, self.anchor = "aa", 2, 2
        self.key("s")
        self.assertEqual(self.document, "ấ")

    def test_stale_snapshot_burst_keeps_every_key_in_order(self):
        history = [("", 0)]
        for key in "tieengs vieetj":
            stale_document, stale_cursor = history[max(0, len(history) - 2)]
            result = self.session.key(key, surrounding=(stale_document, stale_cursor, stale_cursor))
            self.assertTrue(result.handled, key)
            self.assertEqual(result.delete, 0, "never delete on an unconfirmed snapshot")
            self.document = self.document[:self.cursor] + (result.commit or "") + self.document[self.cursor:]
            self.cursor += len(result.commit or "")
            history.append((self.document, self.cursor))
        self.assertEqual(self.document, "tieengs vieetj")

    def test_snapshot_catching_up_composes_whole_word(self):
        for key in "tieeng":
            result = self.session.key(key, surrounding=None if self.document else ("", 0, 0))
            self.document += result.commit or ""
        self.assertEqual(self.document, "tieeng")
        self.cursor = self.anchor = len(self.document)
        self.key("s")
        self.assertEqual(self.document, "tiếng")

    def test_word_started_without_snapshot_composes_once_app_confirms(self):
        # GTK resets on click: the first key of the next word has no snapshot.
        self.document = "x "
        self.cursor = self.anchor = 2
        result = self.session.key("a", surrounding=None)
        self.assertEqual((result.handled, result.commit, result.delete), (True, "a", 0))
        self.document, self.cursor, self.anchor = "x a", 3, 3
        self.key("s")
        self.assertEqual(self.document, "x á")

    def test_word_glued_to_a_letter_is_never_rewritten(self):
        # Negative control for position-free ownership: only a preceding letter
        # lets a stale snapshot match our word, so that case must not rewrite.
        self.document = "ba"
        self.cursor = self.anchor = 2
        self.key("a")
        result = self.key("s")
        self.assertEqual(result.delete, 0)
        self.assertEqual(self.document, "baas")

    def test_app_update_after_zero_delay_burst_composes_whole_word(self):
        self.key("t")
        for key in "ieengs":
            result = self.session.key(key, surrounding=None)
            self.document += result.commit
        self.assertEqual(self.document, "tieengs")
        result = self.session.catch_up((self.document, 7, 7))
        self.assertEqual((result.delete, result.commit), (5, "ếng"))
        self.assertIsNone(self.session.catch_up(("tiếng", 5, 5)).commit, "idempotent once composed")

    def test_catch_up_needs_the_apps_confirmation(self):
        self.key("a")
        self.session.key("s", surrounding=None)
        for snapshot in (("a", 1, 1), ("as", 1, 1), ("as", 2, 0), ("bas", 3, 3), None):
            with self.subTest(snapshot=snapshot):
                result = self.session.catch_up(snapshot)
                self.assertEqual((result.delete, result.commit), (0, None))

    def test_late_update_composes_words_across_a_boundary(self):
        self.key("t")
        for key in "ieengs vieetj":
            self.document += self.session.key(key, surrounding=None).commit
        self.assertEqual(self.document, "tieengs vieetj")
        result = self.session.catch_up((self.document, len(self.document), len(self.document)))
        self.document = self.document[:len(self.document) - result.delete] + (result.commit or "")
        self.assertEqual(self.document, "tiếng việt")

    def test_pending_span_is_bounded(self):
        self.key("t")
        for key in "ieengs " * 10:
            self.document += self.session.key(key, surrounding=None).commit
        self.assertLessEqual(len(self.session.previous), 3)
        self.assertLessEqual(len(self.session.span()), 64)

    def test_unicode_prefix_uses_codepoints_and_preserves_neighbors(self):
        self.document = "🙂a\u0301 "
        self.cursor = self.anchor = len(self.document)
        self.type("as")
        self.assertEqual(self.document, "🙂a\u0301 á")


if __name__ == "__main__":
    unittest.main()
