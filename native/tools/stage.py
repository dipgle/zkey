#!/usr/bin/python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a REVIEW package inside project scratch. Never install/enable anything.

Developer packaging tool only. Python and the legacy engine are NOT shipped as
runtime dependencies. Includes corresponding native Rust source and provenance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tomllib

ROOT=Path(__file__).resolve().parents[2]
BINARY=ROOT/'native/target/release/zkey-native'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_source_hash(source=None):
    source=Path(source) if source is not None else ROOT/'native'
    paths=[source/'Cargo.toml',source/'Cargo.lock',source/'build.rs']
    paths+=sorted(path for path in (source/'src').rglob('*') if path.is_file())
    result=hashlib.sha256()
    for path in sorted(paths):
        name=path.relative_to(source).as_posix().encode();data=path.read_bytes()
        result.update(len(name).to_bytes(8,'little'));result.update(name)
        result.update(len(data).to_bytes(8,'little'));result.update(data)
    return result.hexdigest()


def verify_build(binary,expected_source):
    info=json.loads(subprocess.run([str(binary),'--build-info'],capture_output=True,text=True,check=True).stdout)
    if info.get('source_sha256')!=expected_source:raise ValueError('Native executable is stale or comes from different source; rebuild before staging')
    return info


def stage(destination,binary=BINARY):
    destination=Path(destination).resolve()
    if not destination.is_relative_to(ROOT/'.tmp') or destination==ROOT/'.tmp':
        raise ValueError('Native review packages must stay under project .tmp')
    if destination.exists():raise FileExistsError('Refusing to overwrite an existing review package')
    binary=Path(binary)
    if not binary.is_file() or binary.read_bytes()[:4]!=b'\x7fELF':raise ValueError('Release native ELF binary is missing')
    if platform.machine()!='x86_64':raise ValueError('This package format is verified only on Linux x86_64')
    version=subprocess.run([str(binary),'--version'],capture_output=True,text=True,check=True).stdout.strip()
    if not version.startswith('zkey-native '):raise ValueError('Source executable is not zkey-native')
    binary_hash=digest(binary)
    expected_source=build_source_hash()
    embedded=verify_build(binary,expected_source)
    dependencies=subprocess.run(['readelf','--version-info',str(binary)],capture_output=True,text=True,check=True).stdout
    glibc=max((tuple(map(int,match.split('.'))) for match in re.findall(r'GLIBC_(\d+(?:\.\d+)+)',dependencies)),default=None)
    if glibc is None:raise ValueError('Could not measure native binary libc ABI requirements')
    minimum='.'.join(map(str,glibc))
    cargo=tomllib.loads((ROOT/'native/Cargo.toml').read_text())
    lock=tomllib.loads((ROOT/'native/Cargo.lock').read_text())
    if (cargo.get('dependencies') or cargo.get('build-dependencies') or cargo.get('dev-dependencies')
            or len(lock.get('package',[]))!=1 or lock['package'][0]['name']!='zkey-native'):
        raise ValueError('Native package unexpectedly declares external Cargo dependencies')
    destination.mkdir(parents=True,exist_ok=False)
    marker=destination/'.STAGING';marker.write_text('INCOMPLETE until manifest + final verification\n')
    executable=destination/'usr/bin/zkey-native';executable.parent.mkdir(parents=True)
    shutil.copyfile(binary,executable);executable.chmod(0o755)
    doc=destination/'usr/share/doc/zkey-native';doc.mkdir(parents=True)
    for name in ('LICENSE','NOTICE.md'):shutil.copyfile(ROOT/name,doc/name)
    readme=(ROOT/'native/README.md').read_text().replace('../docs/native-rewrite.md','native-rewrite.md')
    (doc/'README.md').write_text(readme)
    status=ROOT/'docs/native-rewrite.md'
    if not status.is_file():raise ValueError('Native status/limitations document is missing')
    (doc/'native-rewrite.md').write_text(status.read_text().replace('../.tmp/','evidence/'))
    source_docs=doc/'source/docs';source_docs.mkdir(parents=True)
    shutil.copyfile(status,source_docs/'native-rewrite.md')
    for name in ('native-settings-error.png','native-settings-saved.png','native-settings-reopened.png',
                 'native-settings-startup-error.png','native-launcher.png','native-terminal-secret.png',
                 'native-runtime-settings-error.png','native-runtime-settings-recovered.png',
                 'native-gtk3-typing.png','native-gtk4-typing.png','native-webkit-failed.png','native-webkit-safe.png'):
        image=ROOT/'.tmp'/name
        if image.is_file():
            evidence=doc/'evidence';evidence.mkdir(exist_ok=True)
            shutil.copyfile(image,evidence/name)
    # Complete native compilation/packaging source; deliberately excludes target
    # artifacts, scratch, credentials, legacy product code and user settings.
    source=doc/'source/native'
    for name in ('LICENSE','NOTICE.md'):
        target=doc/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    paths=[ROOT/'native/Cargo.toml',ROOT/'native/Cargo.lock',ROOT/'native/build.rs',ROOT/'native/README.md']
    paths+=sorted((ROOT/'native/src').rglob('*'))
    paths+=sorted((ROOT/'native/tools').glob('*.py'))
    source_hash=hashlib.sha256()
    for path in paths:
        if not path.is_file():continue
        relative=path.relative_to(ROOT/'native')
        target=source/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
        source_hash.update(str(relative).encode()+b'\0'+target.read_bytes()+b'\0')
    # Attest the actual COPIED snapshot, not merely the live inputs inspected
    # before copying. A rebuild/edit in between must leave .STAGING and fail.
    if digest(executable)!=binary_hash or digest(binary)!=binary_hash:
        raise ValueError('Native executable changed during staging')
    if build_source_hash(source)!=expected_source or build_source_hash()!=expected_source:
        raise ValueError('Native source changed during staging')
    verify_build(executable,expected_source)
    desktop=destination/'usr/share/applications';desktop.mkdir(parents=True)
    for name,title,command in [('settings','zkey native — Thiết lập (bản thử)','--settings'),('trial','zkey native — Mở ứng dụng thử','--run')]:
        (desktop/f'zkey-native-{name}.desktop').write_text('[Desktop Entry]\nType=Application\n'
            f'Name={title}\nExec=zkey-native {command}\nIcon=input-keyboard\nTerminal=false\nCategories=Utility;\n')
    control=destination/'DEBIAN';control.mkdir()
    (control/'control').write_text(f'Package: zkey-native\nVersion: {cargo["package"]["version"].replace("-dev","~dev")}\n'
        'Architecture: amd64\nMaintainer: zkey contributors <info@dipgle.com>\n'
        f'Depends: libc6 (>= {minimum}), libgcc-s1, libglib2.0-0t64, libgtk-3-0t64, libibus-1.0-5, dbus-daemon, ibus\n'
        'Recommends: gnome-text-editor\nSection: utils\nPriority: optional\n'
        'Description: zkey independent native DEVELOPMENT build, not system-certified\n'
        ' Native settings and private per-application trial. No system IME changes.\n'
        ' Unverified surrounding rewrites are OFF by default. Not a final release.\n')
    info={'version':version,'binary_sha256':digest(executable),'build_source_sha256':embedded['source_sha256'],'package_source_sha256':source_hash.hexdigest(),
          'minimum_glibc':minimum,'architecture':'amd64','cargo_dependencies':0,
          'status':'development-not-release','system_ime_changed':False}
    (doc/'build-info.json').write_text(json.dumps(info,indent=2)+'\n')
    # The installed-data manifest must not require DEBIAN/control, which lives
    # in the separate control archive and is absent after dpkg-deb --extract.
    files=sorted(path for path in (destination/'usr').rglob('*') if path.is_file())
    manifest={str(path.relative_to(destination)):digest(path) for path in files}
    (doc/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    for relative,expected in manifest.items():
        if digest(destination/relative)!=expected:raise RuntimeError('Review package verification failed')
    marker.unlink()
    return info


def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('destination',type=Path)
    parser.add_argument('--deb',action='store_true',help='build a local .deb next to the staged directory; never install')
    args=parser.parse_args()
    info=stage(args.destination)
    print(json.dumps(info,indent=2))
    if args.deb:
        output=args.destination.resolve().with_suffix('.deb')
        if output.exists():raise FileExistsError('Refusing to overwrite an existing .deb')
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(args.destination.resolve()),str(output)],check=True)
        print(f'REVIEW ONLY: {output}')
    print('STAGED ONLY. Not installed, not published, NOT a release-ready product.')


def cli():
    try:main();return 0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print(f'NATIVE PACKAGE FAILED: {error}')
        return 1  # a rejected/broken artifact is RED, never 'not measurable'


if __name__=='__main__':raise SystemExit(cli())
