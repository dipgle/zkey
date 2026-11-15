#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Owner-approved (15/11): install Xvfb so acceptance tests type into a private
# X display instead of the real desktop (no RemoteDesktop portal prompt).
# Run in a visible terminal; the owner types the sudo password.
set -u
LOG=/mnt/data/projects/zkey/.tmp/install-xvfb.log
{
  echo "start $(date -Is)"
  sudo apt-get install -y xvfb
  code=$?
  echo "apt exit=$code"
  command -v Xvfb
  echo "GATE_EXIT=$code"
} 2>&1 | tee "$LOG"
echo
echo "Xong. Có thể đóng tab này."
read -r -t 60 _ || true
