#!/usr/bin/env bash
set -euo pipefail

# 0) Validate VEHICLES env
if [ -z "${VEHICLES:-}" ]; then
  echo "Error: VEHICLES must be set (e.g., 'copter:2')"
  exit 1
fi

# 1) Parse single VEHICLES value (model:count)
model="${VEHICLES%%:*}"
count="${VEHICLES##*:}"

SUPPORTED=(copter rover plane_fw plane_vtol)
if [[ ! " ${SUPPORTED[*]} " =~ " ${model} " ]]; then
  echo "Error: Unsupported model '$model' (must be one of ${SUPPORTED[*]})"
  exit 1
fi
if ! [[ "$count" =~ ^[1-9][0-9]*$ ]]; then
  echo "Error: Invalid count '$count'; must be a positive integer"
  exit 1
fi

# Select finite physical capacity before changing parameters or launching SITL.
COPTER_FRAME=/usr/local/share/ardupilot/copter-frame.json
if [ "$model" = "copter" ] && [ -n "${BATTERY_CAPACITY_MAH:-}" ]; then
  capacity_ah=$(LC_ALL=C awk 'BEGIN {
    value = ENVIRON["BATTERY_CAPACITY_MAH"]
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
    invalid_separator = value ~ /(^|[^0-9])_|_([^0-9]|$)/
    gsub(/_/, "", value)
    # Above this boundary, float32 Ah rounds to 2147483.75 and its mAh
    # conversion rounds to 2147483648, overflowing BATT_CAPACITY (int32).
    max_capacity_mah = 2147483625
    if (invalid_separator ||
        value !~ /^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$/ ||
        value + 0 <= 10 || value + 0 > max_capacity_mah) {
      print "BATTERY_CAPACITY_MAH must be finite, greater than 10, and fit BATT_CAPACITY (int32)" > "/dev/stderr"
      exit 1
    }
    printf "%.17g\n", value / 1000
  }')
  COPTER_FRAME=$(mktemp /tmp/copter-frame-XXXXXX.json)
  # A successful exec retains the frame for SITL; preparation failures remove it.
  trap 'rm -f -- "$COPTER_FRAME"' EXIT
  printf '{"battCapacityAh": %s}\n' "$capacity_ah" > "$COPTER_FRAME"
fi

echo "↪ Spawning $count × $model"
echo "   • Location = ${LAT:-0},${LON:-0},${ALT:-0},${DIR:-0}"
echo

# 2) Tweak params if needed
if [ "$model" = "copter" ]; then
  FILE=/home/atlas/ardupilot/Tools/autotest/default_params/copter.parm
  if [ -f "$FILE" ]; then
    echo "▶ Setting RC_OPTIONS=0 in $FILE"
    grep -q "^RC_OPTIONS" "$FILE" || printf 'RC_OPTIONS\t0\n' >> "$FILE"
    echo "▶ Setting AUTO_OPTIONS=1 in $FILE"
    grep -q "^AUTO_OPTIONS" "$FILE" || printf 'AUTO_OPTIONS\t1\n' >> "$FILE"
  fi
elif [ "$model" = "plane_fw" ]; then
  FILE=/home/atlas/ardupilot/Tools/autotest/models/plane.parm
  if [ -f "$FILE" ]; then
    echo "▶ Setting BATT_MONITOR=4 in $FILE"
    grep -q "^BATT_MONITOR" "$FILE" || printf 'BATT_MONITOR\t4\n' >> "$FILE"
    echo "▶ Setting RC_OPTIONS=0 in $FILE"
    grep -q "^RC_OPTIONS" "$FILE" || printf 'RC_OPTIONS\t0\n' >> "$FILE"
    echo "▶ Setting THR_FAILSAFE=0 in $FILE"
    grep -q "^THR_FAILSAFE" "$FILE" || printf 'THR_FAILSAFE\t0\n' >> "$FILE"
    echo "▶ Setting RTL_AUTOLAND=2 in $FILE"
    grep -q "^RTL_AUTOLAND" "$FILE" || printf 'RTL_AUTOLAND\t2\n' >> "$FILE"
  fi
elif [ "$model" = "plane_vtol" ]; then
  FILE=/home/atlas/ardupilot/Tools/autotest/default_params/quadplane.parm
  if [ -f "$FILE" ]; then
    echo "▶ Setting BATT_MONITOR=4 in $FILE"
    grep -q "^BATT_MONITOR" "$FILE" || printf 'BATT_MONITOR\t4\n' >> "$FILE"
    echo "▶ Setting RC_OPTIONS=0 in $FILE"
    grep -q "^RC_OPTIONS" "$FILE" || printf 'RC_OPTIONS\t0\n' >> "$FILE"
    echo "▶ Setting THR_FAILSAFE=0 in $FILE"
    grep -q "^THR_FAILSAFE" "$FILE" || printf 'THR_FAILSAFE\t0\n' >> "$FILE"
    echo "▶ Setting Q_RTL_MODE=1 in $FILE"
    grep -q "^Q_RTL_MODE" "$FILE" || printf 'Q_RTL_MODE\t1\n' >> "$FILE"
    echo "▶ Setting RTL_AUTOLAND=2 in $FILE"
    grep -q "^RTL_AUTOLAND" "$FILE" || printf 'RTL_AUTOLAND\t2\n' >> "$FILE"
  fi
fi

export VEHICLE_TYPE="$model"

# 3) Defaults
LAT="${LAT:-0}"
LON="${LON:-0}"
ALT="${ALT:-0}"
DIR="${DIR:-0}"
SPEEDUP="${SPEEDUP:-1}"
INSTANCE="${INSTANCE:-1}"

# 4) Select VEHICLE + FRAME
case "$model" in
  copter)     VEH="ArduCopter"; FRAME="+" ;;
  rover)      VEH="Rover";      FRAME="rover" ;;
  plane_fw)   VEH="ArduPlane";  FRAME="plane" ;;
  plane_vtol) VEH="ArduPlane";  FRAME="quadplane" ;;
esac

# 5) Build sim_vehicle.py args
args=(
  --vehicle         "${VEH}"
  -I$INSTANCE
  --custom-location "${LAT},${LON},${ALT},${DIR}"
  --frame           "${FRAME}"
  --no-rebuild
  --speedup         "${SPEEDUP}"
)

if [ "$model" = "copter" ]; then
  # SITL strips leading '/' from paths. Grouped instances run one directory
  # below the launch directory; use a relative model path from either layout.
  model_base=$PWD
  if [ "$count" -gt 1 ]; then
    model_base="$PWD/0"
  fi
  model_path=$(realpath -m --relative-to="$model_base" -- "$COPTER_FRAME")
  # Keep '+' frame defaults (including copter.parm) while selecting the model.
  args+=(--model "+:${model_path}")
fi

if [ "$count" -gt 1 ]; then
  args+=(
    --auto-offset-line 0,10
    --count "$count"
    --auto-sysid
  )
else
  SYSID=$((INSTANCE + 1))
  args+=(
    --sysid "$SYSID"
  )
fi


# 6) Launch sim
echo "▶ Running: sim_vehicle.py ${args[*]}"
exec Tools/autotest/sim_vehicle.py "${args[@]}"
