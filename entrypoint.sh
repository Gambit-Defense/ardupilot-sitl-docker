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

echo "↪ Spawning $count × $model"
echo "   • Location = ${LAT:-0},${LON:-0},${ALT:-0},${DIR:-0}"
echo

# 2) Tweak copter params if needed
if [ "$model" = "copter" ]; then
  FILE=/home/atlas/ardupilot/Tools/autotest/default_params/copter.parm
  if [ -f "$FILE" ]; then
    echo "▶ Setting RC_OPTIONS=0 in $FILE"
    grep -q "^RC_OPTIONS" "$FILE" || printf 'RC_OPTIONS\t0\n' >> "$FILE"
    echo "▶ Setting AUTO_OPTIONS=1 in $FILE"
    grep -q "^AUTO_OPTIONS" "$FILE" || printf 'AUTO_OPTIONS\t1\n' >> "$FILE"
  fi
elif [ "$model" = "plane_fw" ]; then
  FILE=/home/atlas/ardupilot/Tools/autotest/default_params/plane.parm
  if [ -f "$FILE" ]; then
    echo "▶ Setting BATT_MONITOR=4 in $FILE"
    grep -q "^BATT_MONITOR" "$FILE" || printf 'BATT_MONITOR\t4\n' >> "$FILE"
    echo "▶ Setting Q_RTL_MODE=1 in $FILE"
    grep -q "^Q_RTL_MODE" "$FILE" || printf 'Q_RTL_MODE\t1\n' >> "$FILE"
  fi
elif [ "$model" = "plane_vtol" ]; then
  FILE=/home/atlas/ardupilot/Tools/autotest/default_params/quadplane.parm
  if [ -f "$FILE" ]; then
    echo "▶ Setting BATT_MONITOR=4 in $FILE"
    grep -q "^BATT_MONITOR" "$FILE" || printf 'BATT_MONITOR\t4\n' >> "$FILE"
    echo "▶ Setting Q_RTL_MODE=1 in $FILE"
    grep -q "^Q_RTL_MODE" "$FILE" || printf 'Q_RTL_MODE\t1\n' >> "$FILE"
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
