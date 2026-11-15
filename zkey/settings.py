# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native desktop preferences; launch explicitly with python3 -m zkey.settings."""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from .config import Config, config_path, load, record_change, save  # noqa: E402


def main():
    # A broken file must not lock the user out of the screen that fixes it:
    # open with defaults, say so, overwrite only when the user presses Save.
    try:
        config, problem = load(), None
    except (OSError, ValueError) as error:
        config, problem = Config(), f"Tệp thiết lập {config_path()} lỗi ({error}); đang hiện mặc định — bấm Lưu để thay."
    saved = [config if problem is None else None]
    window = Gtk.Window(title="zkey — Thiết lập Telex")
    window.set_border_width(20)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    window.add(box)
    enabled = Gtk.CheckButton(label="Bật gõ tiếng Việt (Telex)")
    enabled.set_active(config.enabled)
    modern = Gtk.CheckButton(label="Đặt dấu hiện đại: hoà, thuý (tắt: hòa, thúy)")
    modern.set_active(config.modern_tone)
    limit = Gtk.SpinButton.new_with_range(8, 256, 8)
    limit.set_value(config.max_word_keys)
    status = Gtk.Label(label=problem or "Thiết lập áp dụng khi chuyển vào ô nhập tiếp theo.")
    status.set_line_wrap(True)
    status.set_max_width_chars(60)
    button = Gtk.Button(label="Lưu thiết lập")

    def on_save(_):
        try:
            new = Config(enabled.get_active(), modern.get_active(), limit.get_value_as_int())
            save(new)
            record_change(saved[0] or Config(), new)
            saved[0] = new
            status.set_text("Đã lưu. Chuyển sang ô nhập để áp dụng.")
        except (OSError, ValueError) as error:
            status.set_text(f"Không lưu được: {error}")

    button.connect("clicked", on_save)
    for widget in (enabled, modern, Gtk.Label(label="Giới hạn phím cho một từ:"), limit, button, status):
        box.pack_start(widget, False, False, 0)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
