# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
import os
from pathlib import Path
import sys
import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, GObject, IBus  # noqa: E402
from .config import load  # noqa: E402
from .core import Core  # noqa: E402
from .session import Result, Session  # noqa: E402

LOG = logging.getLogger("zkey")


class Engine(IBus.Engine):
    __gtype_name__ = "ZkeyEngine"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Fail at startup, with a visible error, if the native library/config is invalid.
        self.session = Session(Core(), load())
        self.surrounding = None
        self.requested = False

    def apply(self, result):
        if result.delete or result.commit:
            # No rewrite may rely on libibus's optimistic post-edit cache.
            self.surrounding = None
        if result.delete:
            self.delete_surrounding_text(-result.delete, result.delete)
        if result.preedit is not None:
            text = IBus.Text.new_from_string(result.preedit)
            if result.preedit:
                text.append_attribute(IBus.AttrType.UNDERLINE, IBus.AttrUnderline.SINGLE, 0, len(result.preedit))
            self.update_preedit_text_with_mode(text, len(result.preedit), bool(result.preedit), IBus.PreeditFocusMode.COMMIT)
        if result.commit:
            self.commit_text(IBus.Text.new_from_string(result.commit))
        return result.handled

    def do_process_key_event(self, keyval, keycode, state):
        if state & IBus.ModifierType.RELEASE_MASK:
            return False
        # Ignore modifier-only events; holding Shift must not commit a partial word.
        name = IBus.keyval_name(keyval) or ""
        if name in {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R", "Caps_Lock", "ISO_Level3_Shift"}:
            return False
        shortcut_mask = (IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK
                         | IBus.ModifierType.SUPER_MASK | IBus.ModifierType.META_MASK
                         | IBus.ModifierType.HYPER_MASK | IBus.ModifierType.MOD5_MASK)
        character = IBus.keyval_to_unicode(keyval)
        key = character if character and character.isprintable() else name
        try:
            self.request_surrounding()
            LOG.debug("key-state supported=%s snapshot=%s protected=%s",
                      self.session.surrounding_supported, self.surrounding is not None, self.session.private)
            return self.apply(self.session.key(key, surrounding=self.surrounding,
                                               shortcut=bool(state & shortcut_mask)))
        except (ValueError, UnicodeError):
            # Previous letters already reached the app; only this key passes on.
            LOG.error("Composition failed; current key passed through; input contents omitted")
            self.session.clear()
            return False

    def do_set_capabilities(self, caps):
        LOG.debug("capabilities=%s", caps)
        self.session.surrounding_supported = bool(caps & IBus.Capabilite.SURROUNDING_TEXT)
        if not self.session.surrounding_supported:
            self.session.clear()
            self.surrounding = None

    def request_surrounding(self):
        """Ask the client for updates once per focus, at the first unprotected key.

        Content type (TERMINAL/PASSWORD) is known by then. Asking earlier makes the
        GTK IBus module query widgets that refuse (VTE) and warn inside the app
        (measured 15/11: caps 41 -> 9 plus a warning). Cached return unused.
        """
        if self.session.surrounding_supported and not self.session.private and not self.requested:
            self.requested = True
            self.get_surrounding_text()

    def do_set_surrounding_text(self, text, cursor, anchor):
        LOG.debug("client surrounding update received")
        # Use incoming app updates, never libibus's optimistically edited cache.
        if not self.session.private:
            self.surrounding = (text.get_text(), cursor, anchor)
            try:
                result = self.session.catch_up(self.surrounding)
            except (ValueError, UnicodeError):
                LOG.error("Catch-up composition failed; text left as the app shows it")
                self.session.clear()
                return
            if result.delete or result.commit:
                LOG.debug("catch-up rewrite delete=%d", result.delete)
                self.apply(result)

    def do_enable(self):
        LOG.debug("enable")
        # IBus clients suppress their initial empty snapshot. This bootstrap can
        # insert the first letter only; apply() invalidates it before that edit.
        self.surrounding = ("", 0, 0)
        self.requested = False

    def do_set_content_type(self, purpose, hints):
        # Mandatory bypass until a cooperating terminal backend is verified:
        # TERMINAL does not expose PTY ECHO, so no safe composition opt-in exists.
        private = purpose in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN,
                              IBus.InputPurpose.TERMINAL)
        private = private or bool(hints & (IBus.InputHints.PRIVATE | IBus.InputHints.HIDDEN_TEXT))
        LOG.debug("content-type purpose=%d hints=%d protected=%s", int(purpose), int(hints), private)
        self.session.private = private
        if private:
            self.session.clear()
            self.surrounding = None
            # Clear client-side content too; hiding is not a cancellation request.
            self.apply(Result(preedit=""))
            self.hide_preedit_text()

    def do_focus_in(self):
        LOG.debug("focus-in")
        self.session.clear()
        self.surrounding = ("", 0, 0)
        self.requested = False
        try:
            self.session.config = load()
        except (OSError, ValueError):
            LOG.error("Invalid config; keeping last valid configuration (no input text logged)")

    def do_focus_in_id(self, object_path, client):
        self.do_focus_in()

    def do_focus_out(self):
        # Each letter was already committed. Never repeat it into another field.
        self.session.clear()
        self.surrounding = None

    def do_focus_out_id(self, object_path):
        self.do_focus_out()

    def do_reset(self):
        # Reset may follow a caret click; never commit into the new location.
        self.session.clear()
        self.surrounding = None
        self.apply(Result(preedit=""))
        self.hide_preedit_text()

    def do_disable(self):
        self.do_reset()


def main():
    logging.basicConfig(level=logging.DEBUG if os.environ.get("ZKEY_TRACE") == "1" else logging.WARNING,
                        format="%(name)s: %(levelname)s: %(message)s")
    IBus.init()
    # Validate dependencies before registering a factory (avoids deferred silent startup failure).
    Core()
    load()
    bus = IBus.Bus()
    if not bus.is_connected():
        raise RuntimeError("IBus unavailable; use the isolated protocol probe or run in a desktop session")
    loop = GLib.MainLoop()
    bus.connect("disconnected", lambda *_: loop.quit())
    factory = IBus.Factory.new(bus.get_connection())
    GObject.type_register(Engine)
    factory.add_engine("zkey", Engine.__gtype__)
    if "--ibus" in sys.argv:
        if not bus.request_name("org.freedesktop.IBus.Zkey", 0):
            raise RuntimeError("Cannot own IBus component name")
    else:
        component = IBus.Component.new("org.freedesktop.IBus.Zkey", "Vietnamese Telex", "0.1.0", "AGPL-3.0-or-later", "zkey contributors", "", "", "zkey")
        component.add_engine(IBus.EngineDesc.new("zkey", "zkey", "Vietnamese Telex", "vi", "AGPL-3.0-or-later", "zkey contributors", "input-keyboard", "us"))
        if not bus.register_component(component):
            raise RuntimeError("IBus component registration rejected")
    if ready := os.environ.get("ZKEY_READY_FILE"):
        path = Path(ready).resolve()
        if not path.is_relative_to(Path(__file__).resolve().parents[1] / ".tmp"):
            raise ValueError("Startup marker must be within zkey/.tmp")
        path.write_text("registered\n")
    loop.run()
    raise RuntimeError("IBus disconnected; engine stopped")


if __name__ == "__main__":
    main()
