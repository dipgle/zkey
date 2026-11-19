# SPDX-License-Identifier: AGPL-3.0-or-later
"""scripts/native-ime.py on a FAKE home: never touches the real desktop, ibus or gsettings."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import contextlib
import importlib.util
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_ime", ROOT / "scripts/native-ime.py")
native_ime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_ime)

ORIGINAL = "[('xkb', 'us'), ('ibus', 'zkey')]"


class StubSystemIme:
    """Stands in for scripts/system-ime.py: records gsettings writes, scripted engine lists."""

    def __init__(self, engines=None, address="unix:path=/x"):
        self.writes = []
        self.engines = list(engines or [])
        self.address = address
        self.sources = ORIGINAL

    def gsettings(self, *args):
        if args[0] == "get":
            return "@a(ss) " + self.sources
        self.writes.append(args[-1])
        return ""

    def daemon_address(self):
        return self.address

    def engine_names(self):
        return self.engines.pop(0) if len(self.engines) > 1 else (self.engines[0] if self.engines else None)


def run(action):
    with contextlib.redirect_stdout(io.StringIO()) as output:
        code = getattr(native_ime, action)()
    return code, output.getvalue()


class NativeImeTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / ".tmp")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        cache = self.home / ".cache/ibus/bus"
        cache.mkdir(parents=True)
        (cache / "registry").write_text("old cache")
        self.stub = StubSystemIme()
        for entry in (patch.dict("os.environ", {"HOME": str(self.home), "ZKEY_SKIP_IBUS": "1"}),
                      patch.object(native_ime, "attest", return_value={}),
                      patch.object(native_ime, "system_ime", return_value=self.stub)):
            entry.start()
            self.addCleanup(entry.stop)

    def test_enable_installs_component_and_binary_moves_cache_and_swaps_the_source(self):
        code, output = run("enable")
        self.assertEqual(code, 0, output)
        p = native_ime.paths()
        self.assertTrue(p["binary"].is_file() and p["binary"].stat().st_mode & 0o111)
        component = ET.fromstring(p["component"].read_text())
        self.assertEqual(component.findtext("name"), "org.freedesktop.IBus.ZkeyNative")
        self.assertEqual(component.findtext("engines/engine/name"), "zkey-native")
        exec_line = component.findtext("exec")
        self.assertEqual(exec_line, f"{p['binary']} --ibus --experimental-rewrite")
        self.assertFalse(p["cache"].exists(), "stale registry cache must be moved aside")
        self.assertEqual(len(list(p["cache"].parent.glob("registry.zkey-bak-*"))), 1)
        self.assertEqual(self.stub.writes, ["[('xkb', 'us'), ('ibus', 'zkey-native')]"])

    def test_trace_option_routes_engine_stderr_to_a_log_with_metadata_tracing_on(self):
        with patch.object(native_ime.sys, "argv", ["native-ime.py", "enable", "--trace"]):
            code, output = run("enable")
        self.assertEqual(code, 0, output)
        p = native_ime.paths()
        command = ET.fromstring(p["component"].read_text()).findtext("exec")
        self.assertIn("ZKEY_NATIVE_TRACE=1", command)
        self.assertIn(str(p["state"] / "engine-trace.log"), command)
        self.assertIn("--ibus --experimental-rewrite", command)
        # Without the flag the engine is NOT traced (default stays quiet).
        run("disable")
        run("enable")
        self.assertNotIn("TRACE", ET.fromstring(p["component"].read_text()).findtext("exec"))

    def test_enable_twice_is_refused_and_disable_restores_everything(self):
        self.assertEqual(run("enable")[0], 0)
        code, output = run("enable")
        self.assertEqual(code, 1)
        self.assertIn("already enabled", output)
        code, output = run("disable")
        self.assertEqual(code, 0, output)
        p = native_ime.paths()
        self.assertFalse(p["binary"].exists() or p["component"].exists())
        self.assertEqual(self.stub.writes[-1], ORIGINAL, "original sources restored verbatim")
        self.assertFalse((p["state"] / "state.json").exists())
        self.assertEqual(run("disable")[0], 1, "nothing left to undo")

    def test_edited_installed_files_are_kept_not_deleted(self):
        run("enable")
        p = native_ime.paths()
        p["component"].write_text(p["component"].read_text() + "<!-- user edit -->")
        code, output = run("disable")
        self.assertEqual(code, 1)
        self.assertTrue(p["component"].exists())
        self.assertIn("KEPT", output)

    def test_stale_binary_is_refused_before_anything_is_written(self):
        with patch.object(native_ime, "attest", side_effect=ValueError("source changed")):
            code, output = run("enable")
        self.assertEqual(code, 1)
        self.assertIn("current source", output)
        p = native_ime.paths()
        self.assertFalse(p["binary"].exists() or p["component"].exists() or p["state"].exists())
        self.assertTrue(p["cache"].exists(), "cache untouched on refusal")
        self.assertEqual(self.stub.writes, [])

    def test_foreign_files_are_never_overwritten(self):
        p = native_ime.paths()
        p["component"].parent.mkdir(parents=True)
        p["component"].write_text("someone else's")
        code, _ = run("enable")
        self.assertEqual(code, 1)
        self.assertEqual(p["component"].read_text(), "someone else's")


class RestartTests(unittest.TestCase):
    """restart_and_wait must read the RUNNING daemon's list: 'restarted' alone is not success."""

    def check(self, engines, want, address="unix:path=/x"):
        stub = StubSystemIme(engines, address)
        with (patch.dict("os.environ", {"ZKEY_SKIP_IBUS": "0"}),
              patch.object(native_ime.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
              patch.object(native_ime.time, "sleep"),
              patch.object(native_ime.time, "monotonic", side_effect=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 100, 200, 300])):
            return native_ime.restart_and_wait(stub, want)

    def test_success_only_when_the_daemon_lists_the_engine(self):
        self.assertTrue(self.check([None, {"xkb:us::eng"}, {"xkb:us::eng", "zkey-native"}], True))
        self.assertFalse(self.check([{"xkb:us::eng"}], True), "daemon never lists it => RED")
        self.assertTrue(self.check([{"xkb:us::eng", "zkey-native"}, {"xkb:us::eng"}], False))
        self.assertFalse(self.check([{"zkey-native"}], False), "still listed after removal => RED")

    def test_no_daemon_address_is_not_measurable_not_green(self):
        self.assertIsNone(self.check([{"zkey-native"}], True, address=None))


if __name__ == "__main__":
    unittest.main()
