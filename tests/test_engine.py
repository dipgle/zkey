# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real handler/apply with a transport editor model; not desktop acceptance."""
import unittest
from zkey.engine import Engine
from gi.repository import IBus
from zkey.core import Core
from zkey.session import Session


class Sink:
    def __init__(self):
        self.session = Session(Core())
        self.session.surrounding_supported = True
        self.surrounding = ("", 0, 0)
        self.requested = False
        self.document = ""
        self.cursor = 0
        self.results, self.preedits, self.commits, self.deletes = [], [], [], []
        self.hidden = 0

    def ack(self):
        Engine.do_set_surrounding_text(self, IBus.Text.new_from_string(self.document), self.cursor, self.cursor)

    def apply(self, result):
        self.results.append(result)
        return Engine.apply(self, result)

    def update_preedit_text_with_mode(self, text, cursor, visible, mode):
        self.preedits.append((text.get_text(), cursor, visible, mode))

    def commit_text(self, text):
        value = text.get_text()
        self.commits.append(value)
        self.document = self.document[:self.cursor] + value + self.document[self.cursor:]
        self.cursor += len(value)
        self.ack()

    def delete_surrounding_text(self, offset, count):
        self.deletes.append((offset, count))
        start = self.cursor + offset
        self.document = self.document[:start] + self.document[start+count:]
        self.cursor = start
        self.ack()

    def hide_preedit_text(self):
        self.hidden += 1

    def do_reset(self):
        Engine.do_reset(self)

    def request_surrounding(self):
        Engine.request_surrounding(self)

    def get_surrounding_text(self):
        self.surrounding_requests = getattr(self, "surrounding_requests", 0) + 1
        return IBus.Text.new_from_string(""), 0, 0


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.sink = Sink()

    def key(self, key, state=0):
        self.sink.ack()
        handled = Engine.do_process_key_event(self.sink, IBus.keyval_from_name(key), 0, state)
        if not handled and not state:
            if key == "BackSpace" and self.sink.cursor:
                cursor = self.sink.cursor
                self.sink.document = self.sink.document[:cursor-1] + self.sink.document[cursor:]
                self.sink.cursor -= 1
            elif len(key) == 1 or key == "space":
                value = " " if key == "space" else key
                cursor = self.sink.cursor
                self.sink.document = self.sink.document[:cursor] + value + self.sink.document[cursor:]
                self.sink.cursor += len(value)
            self.sink.ack()
        return handled

    def test_shift_only_does_not_split_word(self):
        self.key("a")
        self.assertFalse(self.key("Shift_L"))
        self.key("S", IBus.ModifierType.SHIFT_MASK)
        self.assertEqual(self.sink.document, "á")
        self.assertEqual(self.sink.preedits, [])

    def ctrl_tap(self, name="Control_L"):
        self.assertFalse(self.key(name))
        self.assertFalse(self.key(name, IBus.ModifierType.RELEASE_MASK | IBus.ModifierType.CONTROL_MASK))

    def test_ctrl_tap_keeps_the_current_word_as_typed(self):
        # Hà 16/11: "u", Ctrl, "s" must give "us", not "ú".
        self.key("u")
        self.ctrl_tap()
        self.key("s")
        self.assertEqual(self.sink.document, "us")
        self.key("s")
        self.assertEqual(self.sink.document, "uss", "the whole word stays as typed")
        self.key("space")
        for key in "us":
            self.key(key)
        self.assertEqual(self.sink.document, "uss ú", "the next word is Vietnamese again")

    def test_ctrl_tap_freezes_what_is_shown_including_marks(self):
        for key in "aa":
            self.key(key)
        self.ctrl_tap("Control_R")
        self.key("s")
        self.assertEqual(self.sink.document, "âs")

    def test_without_ctrl_tap_us_is_u_acute(self):
        for key in "us":
            self.key(key)
        self.assertEqual(self.sink.document, "ú")

    def test_ctrl_used_for_a_shortcut_is_not_a_tap(self):
        self.key("space")
        self.assertFalse(self.key("Control_L"))
        self.key("x", IBus.ModifierType.CONTROL_MASK)
        self.assertFalse(self.key("Control_L", IBus.ModifierType.RELEASE_MASK | IBus.ModifierType.CONTROL_MASK))
        for key in "aas":
            self.key(key)
        self.assertEqual(self.sink.document, " ấ")

    def test_releasing_the_previous_letter_during_the_tap_still_counts(self):
        self.key("u")
        self.assertFalse(self.key("Control_L"))
        self.key("u", IBus.ModifierType.RELEASE_MASK | IBus.ModifierType.CONTROL_MASK)
        self.assertFalse(self.key("Control_L", IBus.ModifierType.RELEASE_MASK | IBus.ModifierType.CONTROL_MASK))
        self.key("s")
        self.assertEqual(self.sink.document, "us")

    def test_modifier_shortcuts_and_releases(self):
        for mask in (IBus.ModifierType.CONTROL_MASK, IBus.ModifierType.MOD1_MASK,
                     IBus.ModifierType.SUPER_MASK, IBus.ModifierType.MOD5_MASK):
            self.key("a")
            before = self.sink.document
            self.assertFalse(self.key("c", mask))
            self.assertEqual(self.sink.document, before)
            self.assertIsNone(self.sink.results[-1].commit)
        self.key("a")
        before = self.sink.document
        self.assertFalse(self.key("a", IBus.ModifierType.RELEASE_MASK))
        self.assertEqual(self.sink.document, before)

    def test_protected_contexts_pass_through_without_composition(self):
        for purpose, hints in ((IBus.InputPurpose.TERMINAL, 0), (IBus.InputPurpose.PASSWORD, 0),
                               (IBus.InputPurpose.PIN, 0),
                               (IBus.InputPurpose.FREE_FORM, IBus.InputHints.PRIVATE),
                               (IBus.InputPurpose.FREE_FORM, IBus.InputHints.HIDDEN_TEXT)):
            with self.subTest(purpose=purpose, hints=hints):
                self.sink = Sink()
                self.key("a")
                Engine.do_set_content_type(self.sink, purpose, hints)
                self.assertEqual(self.sink.preedits[-1][:3], ("", 0, False))
                self.assertEqual(self.sink.session.raw, "")
                self.sink.commits.clear()
                self.sink.deletes.clear()
                Engine.do_reset(self.sink)
                Engine.do_focus_out(self.sink)
                for key in ("a", "s", "BackSpace", "Escape", "space", "Return"):
                    self.assertFalse(self.key(key))
                self.assertEqual(self.sink.commits, [])
                self.assertEqual(self.sink.deletes, [])
                self.assertIsNone(self.sink.surrounding)
                Engine.do_set_content_type(self.sink, IBus.InputPurpose.FREE_FORM, 0)
                self.assertTrue(self.key("b"))
                self.assertTrue(self.key("space"))  # boundary committed by us, in order
                self.assertEqual(self.sink.commits, ["b", " "])

    def test_reset_disable_and_focus_do_not_duplicate_committed_letters(self):
        for callback in (Engine.do_reset, Engine.do_disable, Engine.do_focus_out):
            with self.subTest(callback=callback.__name__):
                self.sink = Sink()
                self.key("a")
                callback(self.sink)
                self.assertEqual(self.sink.document, "a")
                self.assertEqual(self.sink.commits, ["a"])
                self.assertEqual(self.sink.session.raw, "")
                self.assertIsNone(self.sink.surrounding)

    def test_composition_failure_passes_current_key_exactly_once(self):
        def fail(*_):
            raise ValueError("injected failure")
        self.key("a")
        self.sink.session.core.compose = fail
        with self.assertLogs("zkey", level="ERROR") as logs:
            self.assertFalse(self.key("s"))
        self.assertEqual(self.sink.document, "as")
        self.assertEqual(self.sink.commits, ["a"])
        self.assertEqual(self.sink.session.raw, "")
        self.assertFalse(any("injected failure" in line for line in logs.output))

    def test_surrounding_capability_is_required_not_preedit(self):
        Engine.do_set_capabilities(self.sink, IBus.Capabilite.PREEDIT_TEXT)
        self.assertFalse(self.key("a"))
        self.assertEqual(self.sink.commits, [])
        Engine.do_set_capabilities(self.sink, IBus.Capabilite.SURROUNDING_TEXT)
        self.assertTrue(self.key("a"))

    def test_missing_app_update_never_uses_optimistic_ibus_cache(self):
        self.key("a")
        self.sink.surrounding = None
        self.sink.ack = lambda: None  # the app sends no update
        # Unconfirmed: committed exactly as typed, never a rewrite.
        self.assertTrue(Engine.do_process_key_event(self.sink, ord("s"), 0, 0))
        self.assertEqual(self.sink.deletes, [])
        self.assertEqual(self.sink.document, "as")

    def test_empty_bootstrap_allows_one_insert_then_requires_client_ack(self):
        self.sink.ack = lambda: None
        Engine.do_enable(self.sink)
        self.assertTrue(Engine.do_process_key_event(self.sink, ord("a"), 0, 0))
        self.assertIsNone(self.sink.surrounding)
        self.assertTrue(Engine.do_process_key_event(self.sink, ord("s"), 0, 0))
        self.assertEqual(self.sink.document, "as")
        self.assertEqual(self.sink.deletes, [])

    def test_late_app_update_rewrites_burst_word_in_order(self):
        self.key("t")
        acknowledge, self.sink.ack = self.sink.ack, lambda: None
        for key in "ieengs":
            self.sink.surrounding = None
            self.assertTrue(Engine.do_process_key_event(self.sink, IBus.keyval_from_name(key), 0, 0))
        self.assertEqual(self.sink.document, "tieengs")
        self.sink.ack = acknowledge
        self.sink.ack()
        self.assertEqual(self.sink.document, "tiếng")
        self.assertEqual(self.sink.deletes[-1], (-5, 5))

    def test_protected_context_update_never_rewrites(self):
        self.key("a")
        Engine.do_set_content_type(self.sink, IBus.InputPurpose.PASSWORD, 0)
        # Word state set AFTER entering the protected context: exercises the
        # private guard itself, not only the clear() on content-type change.
        self.sink.session.raw, self.sink.session.text = "as", "as"
        self.sink.document, self.sink.cursor = "as", 2
        self.sink.deletes.clear()
        self.sink.ack()
        self.assertEqual((self.sink.document, self.sink.deletes), ("as", []))

    def test_surrounding_requested_only_from_capable_clients(self):
        # VTE lacks the capability; asking anyway makes libibus warn in the app.
        Engine.do_focus_in(self.sink)
        Engine.do_enable(self.sink)
        Engine.do_set_content_type(self.sink, IBus.InputPurpose.TERMINAL, 0)
        for key in "as":
            Engine.do_process_key_event(self.sink, ord(key), 0, 0)
        self.assertEqual(getattr(self.sink, "surrounding_requests", 0), 0)
        Engine.do_focus_in(self.sink)
        Engine.do_set_content_type(self.sink, IBus.InputPurpose.FREE_FORM, 0)
        for key in "as":
            Engine.do_process_key_event(self.sink, ord(key), 0, 0)
        self.assertEqual(self.sink.surrounding_requests, 1, "once per focus, at the first key")

if __name__ == "__main__":
    unittest.main()
