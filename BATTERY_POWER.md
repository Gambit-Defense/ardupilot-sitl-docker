# Simulated battery power

Propulsion stops below 0.1% charge and becomes available again at 0.1% or
higher. Charge is calculated from the healthy primary battery monitor's
`BATT_CAPACITY` and consumed mAh, without rounding to the displayed percentage.
Missing or invalid accounting preserves the last valid power state; startup
permits propulsion until a valid depleted reading arrives.

The cutoff runs after actuator overrides and before the physics step:

| Launcher frame | Depleted propulsion output |
| --- | --- |
| `+` | Channels 1–4: 1000 PWM |
| `plane` | Channel 3: 1000 PWM |
| `quadplane` | Channels 3 and 5–8: 1000 PWM |
| `rover` | Channel 3: 1500 PWM (neutral) |

Other actuators, physics, sensors, telemetry, and motor spin-down continue.
Restoring charge through the battery-monitor reset command restores power
without restarting SITL; normal arming and failsafe policies still apply.
Custom frames, voltage-only monitors, and recharge-station services are unsupported.

## Build and checks

`Dockerfile` installs `BatteryPower.h` and applies `battery-power.patch` before
compilation. Incompatible source changes fail patch application. `VERSION_TAG`
defaults to `ArduPilot-4.6`; select a commit for reproducible builds.

With Bash and a C++11 compiler, run the threshold, recovery, invalid-input, and
actuator-mapping regressions:

```sh
bash tests/run.sh
```

With Docker and the pinned base image from `tests/Dockerfile.sitl` already
pulled, run from this repository:

```sh
docker build --network none -f tests/Dockerfile.sitl -t local/ardupilot-sitl:battery-power .
bash tests/run-images.sh /tmp/ardupilot-battery-results
```

The image tests use ArduPilot 4.6.3 on Linux amd64, reusing published dependency
layers. The client uses the image's existing Python/pymavlink installation.
Stock and patched `copter`, `rover`, `plane`, and `quadplane` runs check physical
motion, current, and continuing telemetry at 0.05% charge. Rover must also
resume motion when charge returns to 50%, without restarting or rearming.
Append vehicle names to select cases; `PATCHED_SITL_IMAGE` overrides the test
image. Tests disable battery failsafes in isolated containers and retain logs.

VTOL coverage is hover. Aircraft recovery after impact, VTOL transitions,
Neuron/world-model consumers, HITL, and arm64 are not validated.
