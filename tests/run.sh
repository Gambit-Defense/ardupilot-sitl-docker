#!/bin/bash
# Compile and run the simulator battery power regression tests.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf -- "$test_dir"' EXIT
"${CXX:-g++}" -std=c++11 -Wall -Wextra -Werror -pedantic \
    -I"$repo_dir" "$repo_dir/tests/battery_power_test.cpp" -o "$test_dir/battery_power_test"
"$test_dir/battery_power_test"
echo "Battery power regression tests passed."
