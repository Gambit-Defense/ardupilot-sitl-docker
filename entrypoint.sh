#!/usr/bin/env bash
set -e

# 1) any custom pre-start logic you want:
echo "↪ Starting ArduPilot SITL:"
echo "   • Vehicle = ${VEHICLE}"
echo "   • Count   = ${COUNT}"
echo "   • Location= ${LAT},${LON},${ALT},${DIR}"
echo

# 2) override COUNT if passed in as first argument
if [[ $# -ge 1 ]]; then
  COUNT="$1"
  shift
  echo "↪ Overriding COUNT → $COUNT"
fi

# tweak default params file (prevent high throttle error)
FILE=/home/atlas/ardupilot/Tools/autotest/default_params/copter.parm
if [ -f "$FILE" ]; then
  echo "▶ Appending RC_OPTIONS (with tab) to $FILE"
  printf 'RC_OPTIONS\t0\n' >> "$FILE"
else
  echo "⚠ copter.parm not found at $FILE; skipping append"
fi


# build the “always include” args
args=(
  --vehicle    "${VEHICLE}"
  --map
  -I${INSTANCE}
  --custom-location=${LAT},${LON},${ALT},${DIR}
  -w
  --frame      "${MODEL}"
  --no-rebuild
  --speedup    "${SPEEDUP}"
)

# if COUNT > 1, add the extra flags (workaround for bug in ardupilot script)
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

# finally exec the simulator
exec Tools/autotest/sim_vehicle.py "${args[@]}"
