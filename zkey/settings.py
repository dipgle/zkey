"""Native desktop preferences; launch explicitly with python3 -m zkey.settings."""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from .config import Config, load, save  # noqa: E402


def main():
    config = load()
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
    status = Gtk.Label(label="Thiết lập áp dụng khi chuyển vào ô nhập tiếp theo.")
    button = Gtk.Button(label="Lưu thiết lập")

    def on_save(_):
        try:
            save(Config(enabled.get_active(), modern.get_active(), limit.get_value_as_int()))
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
