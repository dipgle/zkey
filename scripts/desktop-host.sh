#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Real native UI typing with synthetic text, using a private application bus.
set -u
cd /mnt/data/projects/zkey || exit 2
/usr/bin/python3 /mnt/data/projects/zkey/scripts/native_acceptance.py > /mnt/data/projects/zkey/.tmp/native-acceptance.log 2>&1
code=$?
printf '\nGATE_EXIT=%s\n' "$code" >> /mnt/data/projects/zkey/.tmp/native-acceptance.log
exit "$code"
