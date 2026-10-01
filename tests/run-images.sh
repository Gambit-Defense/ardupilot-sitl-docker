#!/bin/bash
# Compare stock and patched images through their normal launchers on isolated networks.
set -euo pipefail
tests_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
output_dir=${1:?Usage: run-images.sh OUTPUT_DIR [copter rover plane quadplane]}
shift
mkdir -p "$output_dir"
if [ "$#" -eq 0 ]; then
    set -- copter rover plane quadplane
fi
stock_image=ghcr.io/gambit-defense/ardupilot-sitl-docker@sha256:2293013214ff601d07f72e2f0cff93ea385bb65b3fe7cd384e4678e96d8943eb
patched_image=${PATCHED_SITL_IMAGE:-local/core3756-apm:20260929}
active_container=
status=0

# Remove only the container ID created by this invocation.
cleanup() {
    if [ -n "$active_container" ]; then
        docker rm -f "$active_container" >/dev/null
        active_container=
    fi
}
trap cleanup EXIT

for vehicle in "$@"; do
    case "$vehicle" in
        copter|rover) launcher_vehicle=$vehicle ;;
        plane) launcher_vehicle=plane_fw ;;
        quadplane) launcher_vehicle=plane_vtol ;;
        *) echo "Unsupported vehicle: $vehicle" >&2; exit 2 ;;
    esac
    for variant in stock patched; do
        image=$stock_image
        check_args=()
        if [ "$variant" = patched ]; then
            image=$patched_image
            check_args=(--expect-cutoff)
        fi
        active_container=$(docker run -dit --network none \
            --name "core3756-apm-$$-$variant-$vehicle" \
            -e "VEHICLES=$launcher_vehicle:1" -e INSTANCE=0 -e SPEEDUP=5 \
            -e LAT=47.397742 -e LON=8.545594 -e ALT=488 -e DIR=0 \
            --mount "type=bind,src=$tests_dir,dst=/cutoff,readonly" "$image")
        log="$output_dir/apm-$vehicle-$variant.log"
        if docker exec "$active_container" python3 /cutoff/image_battery_cutoff.py \
            --vehicle "$vehicle" "${check_args[@]}" >"$log" 2>&1; then
            echo "PASS $vehicle $variant"
        else
            echo "FAIL $vehicle $variant ($log)"
            status=1
        fi
        docker logs "$active_container" >"$output_dir/apm-$vehicle-$variant-container.log" 2>&1
        cleanup
    done
done
exit "$status"
