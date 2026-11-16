# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent current-tree identity check for real-UI acceptance artifacts."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('native_attestation',ROOT/'native/tools/stage.py')
attestation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(attestation)


def verify(binary):
    info=attestation.verify_build(binary,attestation.build_source_hash())
    return dict(info,binary_sha256=attestation.digest(binary))
