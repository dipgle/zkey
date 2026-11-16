# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private session-bus socket visible across sandbox mount namespaces.

Keep the host's session-bus authentication/policy; change only the listener and
resolve relative includes against their ORIGINAL directory before relocation.
Never write system D-Bus configuration or use the real desktop runtime.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_CONFIG = Path('/usr/share/dbus-1/session.conf')


def write_config(runtime, source=SYSTEM_CONFIG):
    runtime, source = Path(runtime).resolve(), Path(source).resolve()
    if not runtime.is_relative_to(ROOT / '.tmp'):
        raise ValueError('Private bus runtime must be inside zkey/.tmp')
    tree = ET.parse(source)
    listeners = tree.findall('listen')
    if len(listeners) != 1:
        raise ValueError('Expected exactly one session-bus listener; refusing an unverified configuration')
    listeners[0].text = f'unix:path={runtime}/bus'
    for tag in ('include', 'includedir'):
        for item in tree.findall(tag):
            if (item.text and not Path(item.text).is_absolute()
                    and item.get('selinux_root_relative') != 'yes'):
                item.text = str(source.parent / item.text)
    output = runtime / 'bus.conf'
    tree.write(output, encoding='utf-8', xml_declaration=True)
    output.chmod(0o600)
    return output
