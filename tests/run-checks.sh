#!/usr/bin/env bash
# Exercise battery capacity and frame selection without starting SITL.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash -n "$repo/entrypoint.sh"
python3 "$repo/tests/test_entrypoint.py"
bash "$repo/tests/test_entrypoint_shell.sh"
