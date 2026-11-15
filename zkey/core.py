import ctypes
from pathlib import Path


class Core:
    def __init__(self, library=None):
        library = library or Path(__file__).resolve().parents[1] / "target/release/libzkey_core.so"
        self.library = ctypes.CDLL(str(library))
        self.call = self.library.zkey_compose
        self.call.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_bool]
        self.call.restype = ctypes.c_ssize_t
        self.output = ctypes.create_string_buffer(256 * 4)

    def compose(self, raw, modern=True):
        data = raw.encode("utf-8")
        size = self.call(data, len(data), self.output, len(self.output), modern)
        if size < 0:
            raise ValueError(f"Native composition failed ({size})")
        return self.output.raw[:size].decode("utf-8")
