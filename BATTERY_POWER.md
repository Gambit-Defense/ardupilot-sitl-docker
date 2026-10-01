# Simulated battery power

The SITL build includes a battery-based propulsion cutoff. A healthy primary
battery monitor with positive `BATT_CAPACITY` and finite, nonnegative consumed
mAh disables propulsion below 0.1% remaining charge. The percentage is computed
from capacity and consumed mAh without rounding to the MAVLink integer display.
Exactly 0.1% and higher permit propulsion, matching Unity's battery threshold.

Restoring valid charge to at least 0.1% restores power in the same SITL process.
ArduPilot's battery-monitor reset command can restore that charge. The gate does
not arm the autopilot or generate commands; normal arming and control policies
still apply. New actuator commands or mode changes cannot bypass low charge.
Missing, unhealthy, disabled, or invalid accounting retains the last valid power
state. Startup permits propulsion until a valid depleted reading arrives.

The cutoff runs after the final local actuator override and before the physics
step. Physics, gravity, aerodynamic forces, sensors, and MAVLink continue.
Flight-controller arming, mode, and failsafe policies are unchanged. The existing
motor model retains its configured spin-down response.

The supported frames are the four built-in frames selected by `entrypoint.sh`:

| Frame | Propulsion output below 0.1% | Other outputs |
| --- | --- | --- |
| `+` | Channels 1–4: 1000 PWM | Preserved |
| `plane` | Channel 3: 1000 PWM | Preserved |
| `quadplane` | Channels 3 and 5–8: 1000 PWM | Preserved |
| `rover` | Channel 3: 1500 PWM (neutral) | Preserved |

Other frame strings, including custom model JSON, reversible planes and skid
rovers, remain unchanged. They need their own verified propulsion mappings.
The primary monitor must provide current integration; a voltage-only monitor or
an external percentage without consumed mAh is unsupported. The image does not
implement a recharge-station service.

## Build and regression checks

`Dockerfile` applies `battery-power.patch` and installs `BatteryPower.h` before
building. Patch application fails the build if the source no longer matches.
`VERSION_TAG` retains the existing `ArduPilot-4.6` default; use a commit for a
reproducible image build.

With Bash and a C++11 compiler, run:

```sh
bash tests/run.sh
```

The focused C++ suite checks all four actuator mappings, power at exactly 0.1%,
cutoff at 0.05% and zero, recovery, repeated depletion, and invalid accounting.
These helper tests do not simulate vehicle dynamics.

With Docker and the pinned published APM base image available, run from this
repository:

```sh
docker build --network none -f tests/Dockerfile.sitl -t local/core3756-apm:20260929 .
bash tests/run-images.sh /tmp/core3756-apm-results
```

The local image compiles Copter, Rover, Plane and Sub against ArduPilot
`12a6efea39425b084234551355470341f71f79d4` (4.6.3), using the base image's source
and GCC 9.4 compiler on Linux amd64. It preserves the normal launcher and reuses
the published dependency layers instead of rebuilding all Ubuntu prerequisites.

The runner compares stock and patched images through the `VEHICLES` launcher
and MAVProxy. It checks `SIM_STATE` ground truth, motor current, advancing time
and heartbeats. The client sets charge to 0.05% through `MAV_CMD_BATTERY_RESET`;
a large test capacity keeps that charge positive during the observation.
Patched cases must lose propulsion before exact zero. Rover additionally must
resume motion after restoring charge to 50%, without restarting or rearming.
Battery failsafe actions are disabled only in the disposable test instances.
The client uses Python/pymavlink already available in the APM image.

Optional vehicle arguments after the output directory select `copter`, `rover`,
`plane`, or `quadplane`. `PATCHED_SITL_IMAGE` overrides the local image tag.
The runner publishes no host ports, removes only its own containers, and retains
logs and the local image. VTOL coverage is hover. Aircraft recovery after impact,
VTOL transitions, Neuron/world-model consumers, HITL, and arm64 are not exercised.

For a source checkout with compiled SITL binaries, the separate direct-process
check supports Copter and Rover:

```sh
python3 tests/flight_battery_cutoff.py --source /home/atlas/ardupilot --expect-cutoff
python3 tests/flight_battery_cutoff.py --source /home/atlas/ardupilot --vehicle rover --expect-cutoff
```

Run it only in an isolated test container. It commands motion and changes battery
state. Omit `--expect-cutoff` for the stock-image behavior assertion.
