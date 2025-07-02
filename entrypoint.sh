#!/usr/bin/env bash
set -e

# 1) Pre-start logging
echo "↪ Starting ArduPilot SITL:"
echo "   • Vehicle Type = ${VEHICLE_TYPE}"
echo "   • Count        = ${COUNT}"
echo "   • Location     = ${LAT},${LON},${ALT},${DIR}"
echo

# 2) Override COUNT if passed as first arg
if [[ $# -ge 1 ]]; then
  COUNT="$1"
  shift
  echo "↪ Overriding COUNT → $COUNT"
fi

# 3) Tweak default params file (prevent high throttle error)
FILE=/home/atlas/ardupilot/Tools/autotest/default_params/copter.parm
if [ -f "$FILE" ]; then
  echo "▶ Appending RC_OPTIONS (with tab) to $FILE"
  printf 'RC_OPTIONS\t0\n' >> "$FILE"
else
  echo "⚠ copter.parm not found at $FILE; skipping append"
fi

# 4) Pick the right vehicle & frame based on VEHICLE_TYPE
case "$VEHICLE_TYPE" in
  iris)
    VEHICLE="ArduCopter"
    FRAME="+"
    ;;
  standard_vtol)
    VEHICLE="Plane"
    FRAME="quadplane"
    ;;
  *)
    echo "⚠ Unknown VEHICLE_TYPE '$VEHICLE_TYPE', defaulting to ArduCopter/+"
    VEHICLE="ArduCopter"
    FRAME="+"
    ;;
esac

# 5) Build the common argument list
args=(
  --vehicle         "${VEHICLE}"
  --map
  -I"${INSTANCE}"
  --custom-location="${LAT},${LON},${ALT},${DIR}"
  -w
  --frame           "${FRAME}"
  --no-rebuild
  --speedup         "${SPEEDUP}"
)

# 6) If COUNT > 1, append the multi-instance flags
if [ "${COUNT}" -gt 1 ]; then
  echo "↪ Including multi-instance flags for COUNT=${COUNT}"
  args+=( 
    --auto-offset-line 0,10 
    --auto-sysid 
    --count "${COUNT}"
  )
else
  echo "↪ Single-instance mode (skipping --auto-offset-line, --auto-sysid, --count)"
fi

# 7) Exec the simulator
exec Tools/autotest/sim_vehicle.py "${args[@]}"
