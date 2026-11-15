#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepare reviewable user-local install files INSIDE the project. Does not install."""
from pathlib import Path
import argparse
import shlex
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def desktop_quote(argument):
    """Desktop Entry Exec quoting: double quotes only; escape " ` $ \\ inside."""
    if not any(c in argument for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return argument
    return '"' + "".join("\\" + c if c in '"`$\\' else c for c in argument) + '"'


def stage(destination, prefix):
    destination = Path(destination).resolve()
    prefix = Path(prefix).expanduser().resolve()
    if not destination.is_relative_to(ROOT / ".tmp"):
        raise ValueError("Staging destination must be under zkey/.tmp")
    library = ROOT / "target/release/libzkey_core.so"
    line = ROOT / "target/release/zkey-line"
    if not library.is_file() or not line.is_file():
        raise FileNotFoundError("Build release core and zkey-line before staging (cargo build --release)")
    package = destination / "lib/zkey"
    (package / "zkey").mkdir(parents=True, exist_ok=True)
    (package / "target/release").mkdir(parents=True, exist_ok=True)
    (package / "shell").mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "zkey").glob("*.py"):
        shutil.copy2(source, package / "zkey" / source.name)
    shutil.copy2(library, package / "target/release/libzkey_core.so")
    # Shell plugin finds zkey-line at <its dir>/../target/release (shell/zkey.bash).
    shutil.copy2(line, package / "target/release/zkey-line")
    shutil.copy2(ROOT / "shell/zkey.bash", package / "shell/zkey.bash")
    for notice in ("LICENSE", "NOTICE.md"):
        shutil.copy2(ROOT / notice, package / notice)
    desktop = destination / "share/applications/zkey.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text("[Desktop Entry]\nType=Application\nName=zkey — Gõ tiếng Việt\n"
                       "Comment=Mở Text Editor với Telex theo từng phím\n"
                       f"Exec={desktop_quote(str(prefix / 'bin/zkey'))} --run\n"
                       "Icon=input-keyboard\nTerminal=false\nCategories=Utility;TextEditor;\nStartupNotify=true\n")
    launcher = destination / "bin/zkey"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/usr/bin/python3\nimport sys\nsys.path.insert(0, "
        + repr(str(prefix / "lib/zkey")) + ")\n"
        + "if sys.argv[1:2] == ['--run']:\n    sys.argv.pop(1)\n    from zkey.launch import main\n"
        + "elif '--settings' in sys.argv:\n    from zkey.settings import main\n"
        + "else:\n    from zkey.engine import main\nraise SystemExit(main())\n")
    launcher.chmod(0o755)
    component = ET.Element("component")
    command = shlex.quote(str(prefix / "bin/zkey"))
    for key, value in {"name": "org.freedesktop.IBus.Zkey", "description": "zkey Vietnamese Telex",
        "exec": command + " --ibus", "version": "0.1.0", "license": "AGPL-3.0-or-later",
        "author": "zkey contributors", "textdomain": "zkey"}.items():
        ET.SubElement(component, key).text = value
    engine = ET.SubElement(ET.SubElement(component, "engines"), "engine")
    for key, value in {"name": "zkey", "longname": "zkey", "description": "Vietnamese Telex",
        "language": "vi", "license": "AGPL-3.0-or-later", "author": "zkey contributors",
        "icon": "input-keyboard", "layout": "us", "symbol": "Z",
        "setup": command + " --settings"}.items():
        ET.SubElement(engine, key).text = value
    output = destination / "share/ibus/component/zkey.xml"
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(component)
    ET.ElementTree(component).write(output, encoding="utf-8", xml_declaration=True)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT / ".tmp/stage")
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    args = parser.parse_args()
    print("STAGED ONLY:", stage(args.destination, args.prefix))
    print("Desktop not changed. Review and real UI acceptance remain required.")


if __name__ == "__main__":
    main()
