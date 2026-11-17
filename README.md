ArduPilot Software-in-the-Loop Simulator Docker Container
=========================================================

The purpose of this is to run an ArduPilot SITL from within Docker.

This is based on adarku SITL docker implementation

Running
---------

Pull Down

`docker pull ghcr.io/gambit-defense/ardupilot-sitl-docker:latest`

Run

`docker run -it --rm ghcr.io/gambit-defense/ardupilot-sitl-docker:latest`

⚠️ **DEPRECATED:** This section is obsolete and no longer maintained.:
DockerHub
---------

A pre-built Docker image is available on DockerHub at:

https://hub.docker.com/r/radarku/ardupilot-sitl

- To download it, run `docker pull radarku/ardupilot-sitl`
- To run it, run `docker run -it --rm -p 5760:5760 radarku/ardupilot-sitl`
- To use it with [Docker Compose](https://docs.docker.com/compose/), add the following service to your `docker-compose.yml` file:
    - You can launch it with `docker-compose up -d`
    - If you update your `docker-compose.yml`, you can restart your container by running `docker-compose up -d` without getting the container ID and killing the container manually. See https://github.com/radarku/ardupilot-sitl-docker/issues/3
    - To check the logs in `ArduCopter.log`, run `docker exec -it "$FOLDER_NAME_ardupilot-sitl_1" watch -n 1 "cat /tmp/ArduCopter.log"`, where you should update `$FOLDER_NAME` with the folder containing the `docker-compose.yml`.

```yml
services:
  ardupilot-sitl:
    image: radarku/ardupilot-sitl
    platform: linux/amd64
    tty: true
    ports:
      - 5760:5760
```

Quick Start
-----------

If you'd rather build the docker image yourself:

`docker build --tag ardupilot_sitl_docker .`

You can now use the `--build-arg` option to specify which branch or tag in the ardupilot
repository you'd like to use. Here's an example:

`docker build --tag ardupilot_sitl_docker --build-arg COPTER_TAG=Copter-4.0.1_sitl_docker .`

If no COPTER_TAG is supplied, the build will use the default defined in the Dockerfile, currently set at Copter-4.0.3

To run the image:

`docker run -it --rm --network host ardupilot_sitl_docker`

Building and Pushing to GHCR
----------------------------

The **Build and Publish Docker Image** workflow builds the existing Dockerfile on
native AMD64 (`ubuntu-24.04`) and ARM64 (`ubuntu-24.04-arm`) runners. Both builds use
the same repository commit and one resolved ArduPilot commit from the Dockerfile's
`VERSION_TAG`. Each runner checks the launcher, executes all four simulator
binaries, and requires a live copter heartbeat before publishing its image.

Pull requests targeting `develop` or `master` run both builds. Same-repository PRs
publish a two-platform test tag after both native checks pass:
`pr-<number>.<source-prefix>-<run-id>-<attempt>`. Fork PRs run the builds and startup
checks. Manual runs publish `build-<source-prefix>-<run-id>-<attempt>` tags. The run
summary contains the exact `docker pull` command. Pushes to `master` also update
`latest` after both architectures pass.

Startup evidence is saved in the `native-smoke-amd64` and `native-smoke-arm64`
artifacts. These checks cover binary execution and copter startup; flight
qualification runs in Praxis using the published image index.

With Docker running natively on a supported Linux architecture, build and check
the image locally (use `linux/arm64` on an ARM64 Docker host):

```bash
docker build --platform linux/amd64 --tag ardupilot-sitl:local .
bash tests/smoke-image.sh ardupilot-sitl:local linux/amd64 /tmp/ardupilot-smoke
```

The smoke check uses the image's installed MAVLink tools and an isolated
container network. It saves image metadata, binary output, the heartbeat, and
simulator logs in the evidence directory, then removes its container.

Options
-------

There are a number of options available to configure the simulator, for example, to run an ArduRover instance on port 5761, you could:

`docker run -it --rm -p 5761:5760 --env VEHICLE=APMrover2 ardupilot`

We also have an example `env.list` file which can help you maintain your options and called like so:

`docker run -it --rm -p 5761:5760 --env-file env.list ardupilot`

The full list of options and their default values is:

```
INSTANCE    0
LAT         42.3898
LON         -71.1476
ALT         14
DIR         270
MODEL       +
SPEEDUP     1
VEHICLE     arducopter
```

So, for example, you could issue a command such as:

```
docker run -it --rm -p 5761:5760 \
   --env VEHICLE=APMrover2 \
   --env MODEL=rover-skid \
   --env LAT=39.9656 \
   --env LON=-75.1810 \
   --env ALT=276 \
   --env DIR=180 \
   --env SPEEDUP=2 \
   ardupilot
```

Vehicles and their corresponding models are listed below:

```
ArduCopter: octa-quad|tri|singlecopter|firefly|gazebo-
    iris|calibration|hexa|heli|+|heli-compound|dodeca-
    hexa|heli-dual|coaxcopter|X|quad|y6|IrisRos|octa
APMRover2: rover|gazebo-rover|rover-skid|calibration
ArduSub: vectored
ArduPlane: gazebo-zephyr|CRRCSim|last_letter|plane-
    vtail|plane|quadplane-tilttri|quadplane|quadplane-
    tilttrivec|calibration|plane-elevon|plane-
    tailsitter|plane-dspoilers|quadplane-tri
    |quadplane-cl84|jsbsim
```

Copter battery capacity
-----------------------

Copter instances use `copter-frame.json` through ArduPilot's `+:<path>.json`
model syntax, retaining `--frame +` and the stock copter parameter defaults.
The model path is relative to each SITL instance directory. Its default physical capacity is 3.3 Ah, which also supplies the
3,300 mAh default reported capacity. `BATTERY_CAPACITY_MAH` overrides both;
for example, `-e VEHICLES=copter:2 -e BATTERY_CAPACITY_MAH=6600` starts two copters
with 6.6 Ah each. The override must be finite, greater than 10 mAh, and fit a
signed 32-bit reported capacity after conversion. CONGO passes its
`--battery-capacity-mah` option to this environment
variable while retaining its Neuron parameter override.
The entrypoint uses the image's existing `awk` for capacity validation and
conversion, and `realpath` for relative model paths.

ArduPilot's existing battery and motor physics reduce thrust as voltage drops
and remove thrust below the motor model's voltage cutoff. Physical loss of
lift can precede displayed 0% charge. Normal low-battery failsafes may land the
vehicle first. Firmware source, other vehicle frames, and network links are
unchanged. Recovery requires restarting the affected simulation; no live
recharge control is provided.

With Bash, awk, GNU coreutils, and Python 3 available, run `bash tests/run-checks.sh`.
These checks exercise capacity conversion and launch
arguments without starting SITL. Flight behavior requires a built SITL image.

Pull request validation
-----------------------

PR checks use the shared workflows in
[Gambit-Defense/Automation](https://github.com/Gambit-Defense/Automation):

- **Validate PR Title** calls `pr-title.yml@v1` on opened, edited, reopened and
  synchronize events. Accepted titles and release exceptions follow the shared
  policy.
- **Run checks** calls `pre-commit.yml@v1` on opened, reopened, synchronize and
  ready-for-review events, using Python 3.13 and pre-commit 4.2.0. The required
  check passes only when the shared validation succeeds.

`.pre-commit-config.yaml` checks all tracked files for YAML, JSON, Python and
Bash syntax, trailing whitespace and final newlines. It also runs the existing
battery and entrypoint checks through `bash tests/run-checks.sh`. The separate
battery workflow retains those native checks on pushes and pull requests.

With Python 3.13, Bash, awk and GNU coreutils available, run the same checks
locally:

```sh
python3 -m pip install pre-commit==4.2.0
pre-commit run --all-files --show-diff-on-failure
```

Run `pre-commit install` to enable the hooks locally. The checks validate source
and launch arguments without starting SITL; flight behavior requires a built
SITL image.
