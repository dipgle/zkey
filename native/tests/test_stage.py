# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('native_stage',ROOT/'native/tools/stage.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)


class NativePackageTests(unittest.TestCase):
    def test_cli_rejected_package_is_failure_not_not_measurable(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            result=subprocess.run([sys.executable,str(ROOT/'native/tools/stage.py'),folder],capture_output=True,text=True)
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)

    def test_copied_source_or_binary_race_keeps_package_incomplete(self):
        copy=stage.shutil.copyfile
        for suffix in ('src/main.rs','usr/bin/zkey-native'):
            with self.subTest(suffix=suffix),tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
                target=Path(folder)/'pkg'
                def changed_copy(source,destination,*args,**kwargs):
                    result=copy(source,destination,*args,**kwargs)
                    if str(destination).endswith(suffix):
                        with Path(destination).open('ab') as output:output.write(b'\n')
                    return result
                with patch.object(stage.shutil,'copyfile',side_effect=changed_copy):
                    with self.assertRaises(ValueError):stage.stage(target)
                self.assertTrue((target/'.STAGING').is_file())
    def test_real_binary_source_attestation_is_red_for_wrong_source_then_green(self):
        with self.assertRaises(ValueError):stage.verify_build(stage.BINARY,'0'*64)
        self.assertEqual(stage.verify_build(stage.BINARY,stage.build_source_hash())['source_sha256'],stage.build_source_hash())
    def test_refuses_outside_scratch_before_creating_anything(self):
        with self.assertRaises(ValueError):stage.stage(ROOT/'native/forbidden-output')

    def test_missing_binary_does_not_create_a_false_package(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            target=Path(folder)/'pkg'
            with self.assertRaises(ValueError):stage.stage(target,Path(folder)/'missing')
            self.assertFalse(target.exists())

    def test_native_package_has_source_manifest_no_python_runtime_or_ime_activation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as folder:
            target=Path(folder)/'pkg';info=stage.stage(target)
            self.assertEqual(info['cargo_dependencies'],0)
            self.assertEqual(info['status'],'development-not-release')
            self.assertTrue((target/'usr/share/doc/zkey-native/source/native/src/main.rs').is_file())
            self.assertFalse((target/'usr/share/ibus/component').exists())
            self.assertFalse((target/'DEBIAN/postinst').exists())
            self.assertIn('Terminal=false',(target/'usr/share/applications/zkey-native-settings.desktop').read_text())
            manifest=json.loads((target/'usr/share/doc/zkey-native/manifest.json').read_text())
            for name,expected in manifest.items():self.assertEqual(stage.digest(target/name),expected)
            self.assertEqual(info['binary_sha256'],stage.digest(target/'usr/bin/zkey-native'))
            (target/'usr/bin/zkey-native').write_text('user modification')
            with self.assertRaises(FileExistsError):stage.stage(target)
            self.assertEqual((target/'usr/bin/zkey-native').read_text(),'user modification')


if __name__=='__main__':unittest.main()
