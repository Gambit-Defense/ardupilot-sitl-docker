#!/usr/bin/env bash
# Verify native simulator binaries and a live copter heartbeat in an isolated container.
set -euo pipefail
image=${1:?Usage: smoke-image.sh IMAGE PLATFORM OUTPUT_DIRECTORY [ARDUPILOT_COMMIT]}
platform=${2:?A native linux/amd64 or linux/arm64 platform is required}
output=${3:?An evidence directory is required}
upstream=${4:-}
case "$platform" in
  linux/amd64|linux/arm64) ;;
  *) echo "Unsupported platform: $platform" >&2; exit 1 ;;
esac
architecture=$(docker info --format '{{.Architecture}}')
case "$architecture" in
  x86_64) architecture=amd64 ;;
  aarch64) architecture=arm64 ;;
esac
test "$(docker info --format '{{.OSType}}')/$architecture" = "$platform"
test "$(docker image inspect "$image" --format '{{.Os}}/{{.Architecture}}')" = "$platform"
mkdir -p "$output"
docker image inspect "$image" > "$output/image.json"
docker run --rm --network none --entrypoint timeout "$image" 30s bash -ec '
  for binary in arducopter ardurover arduplane ardusub; do
    build/sitl/bin/"$binary" --help
  done
' > "$output/binaries.log" 2>&1
if [[ -n "$upstream" ]]; then
  actual=$(docker run --rm --network none --entrypoint git "$image" rev-parse HEAD)
  test "$actual" = "$upstream"
fi
container=

# Retain startup evidence and remove only the container started by this check.
cleanup() {
  status=$?
  trap - EXIT
  if [[ -n "$container" ]]; then
    docker logs "$container" > "$output/simulator.log" 2>&1 || true
    docker rm -f "$container" > /dev/null || status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
container=$(docker run -dit --network none -e VEHICLES=copter:1 -e INSTANCE=0 \
  -e LAT=34.383 -e LON=-118.468 -e ALT=100 "$image")
docker exec -i "$container" timeout 150s python3 - > "$output/heartbeat.json" <<'PY'
import json
from pymavlink import mavutil

connection = mavutil.mavlink_connection("udpin:127.0.0.1:14550")
try:
    heartbeat = connection.wait_heartbeat(timeout=120)
    if heartbeat is None:
        raise RuntimeError("ArduPilot did not send a heartbeat within 120 seconds")
    assert heartbeat.get_srcSystem() == 1, heartbeat
    assert heartbeat.type == mavutil.mavlink.MAV_TYPE_QUADROTOR, heartbeat
    assert heartbeat.autopilot == mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA, heartbeat
    print(json.dumps({"system_id": heartbeat.get_srcSystem(), "heartbeat": heartbeat.to_dict()}))
finally:
    connection.close()
PY
echo "Native $platform binaries and copter heartbeat passed."
