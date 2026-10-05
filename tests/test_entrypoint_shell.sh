#!/usr/bin/env bash
# Exercise shell-only launch preparation and reject failures before SITL starts.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
REAL_REALPATH=$(command -v realpath)
REAL_MKTEMP=$(command -v mktemp)
export REAL_REALPATH REAL_MKTEMP
export CAPTURE="$temporary/arguments"
export FRAME_CAPTURE="$temporary/frame.json"
export ALLOCATION="$temporary/allocation"
export FRAME_FIXTURE="$repo/copter-frame.json"
work="$temporary/firmware with spaces"
mkdir -p "$temporary/bin" "$work/Tools/autotest"

cat > "$temporary/bin/python3" <<'SH'
#!/usr/bin/env bash
echo 'Unexpected Python invocation during shell launch preparation' >&2
exit 97
SH
cat > "$temporary/bin/realpath" <<'SH'
#!/usr/bin/env bash
if [ "${FAIL_REALPATH:-0}" = 1 ]; then exit 43; fi
exec "$REAL_REALPATH" "$@"
SH
cat > "$temporary/bin/mktemp" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [ "${FAIL_MKTEMP:-0}" = 1 ]; then exit 42; fi
path=$("$REAL_MKTEMP" "$@")
printf '%s\n' "$path" > "$ALLOCATION"
printf '%s\n' "$path"
SH
cat > "$work/Tools/autotest/sim_vehicle.py" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$CAPTURE"
base=$PWD
model=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --model) model=$2; shift ;;
    --count) base="$PWD/0"; mkdir -p "$base"; shift ;;
  esac
  shift
done
if [[ "$model" == +:* ]]; then
  path=$("$REAL_REALPATH" -m -- "$base/${model#*:}")
  if [ "$path" = /usr/local/share/ardupilot/copter-frame.json ]; then
    cp -- "$FRAME_FIXTURE" "$FRAME_CAPTURE"
  else
    cat -- "$path" > "$FRAME_CAPTURE"
    rm -- "$path"
  fi
fi
exit "${SIM_EXIT:-0}"
SH
chmod +x "$temporary/bin/"* "$work/Tools/autotest/sim_vehicle.py"
export PATH="$temporary/bin:$PATH"

# Run one entrypoint invocation without retaining a preceding case's artifacts.
run() {
  rm -f -- "$CAPTURE" "$FRAME_CAPTURE" "$ALLOCATION"
  status=0
  (cd -- "$work" && env VEHICLES=copter:1 INSTANCE=0 BATTERY_CAPACITY_MAH= \
    "$@" bash "$repo/entrypoint.sh") > "$temporary/output" 2>&1 || status=$?
}

# Compare generated JSON's capacity numerically using the image's existing awk.
expect_capacity() {
  if [ "$status" -ne 0 ]; then cat "$temporary/output" >&2; exit 1; fi
  test -f "$CAPTURE"
  awk -F: -v expected="$1" '/"battCapacityAh"/ {
    gsub(/[}[:space:]]/, "", $2); found = 1; valid = ($2 + 0 == expected)
  } END { exit !(found && valid) }' "$FRAME_CAPTURE"
}

for count in 1 3; do
  run "VEHICLES=copter:$count"
  expect_capacity 3.3
  for value in 6600 6.6e3 +6600. 6_600 $' \t6600\n'; do
    run "VEHICLES=copter:$count" "BATTERY_CAPACITY_MAH=$value"
    expect_capacity 6.6
  done
  run "VEHICLES=copter:$count" BATTERY_CAPACITY_MAH=2147483625
  expect_capacity 2147483.625
done

for value in 2147483625.0000002 2147483626 2147483647 1e309 nan inf \
  10 1e-300 -11 '11oops' '11\n' '0x100' '1__100' '1100_' '1e_3'; do
  run "BATTERY_CAPACITY_MAH=$value"
  test "$status" -ne 0
  test ! -e "$CAPTURE"
  test ! -e "$ALLOCATION"
  grep -q BATTERY_CAPACITY_MAH "$temporary/output"
done

run BATTERY_CAPACITY_MAH=6600 FAIL_MKTEMP=1
test "$status" -eq 42
test ! -e "$CAPTURE"
run BATTERY_CAPACITY_MAH=6600 FAIL_REALPATH=1
test "$status" -eq 43
test ! -e "$CAPTURE"
test ! -e "$(cat "$ALLOCATION")"
run SIM_EXIT=23
test "$status" -eq 23
test -f "$CAPTURE"
echo 'APM shell preparation checks passed'
