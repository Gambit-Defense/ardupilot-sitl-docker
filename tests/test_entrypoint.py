"""Exercise entrypoint arguments and finite battery frame generation."""

import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def launch(tmp_path):
    """Capture sim_vehicle arguments without running an autopilot."""
    program = tmp_path / "Tools/autotest/sim_vehicle.py"
    program.parent.mkdir(parents=True)
    program.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
from tempfile import TemporaryDirectory
args = sys.argv[1:]
frame = args[args.index('--frame') + 1]
model = args[args.index('--model') + 1] if '--model' in args else frame
capacity = None
if model.startswith('+:'):
    base = Path.cwd() / '0' if '--count' in args else Path.cwd()
    path = (base / model[2:]).resolve()
    if path == Path('/usr/local/share/ardupilot/copter-frame.json'):
        path = Path(os.environ['FRAME_FIXTURE'])
    capacity = json.loads(path.read_text())['battCapacityAh']
    if str(path).startswith('/tmp/copter-frame-'):
        path.unlink()
Path(os.environ['CAPTURE']).write_text(json.dumps({'args': args, 'frame': frame, 'capacity': capacity}))
""")
    program.chmod(0o755)
    capture = tmp_path / "arguments.json"

    def run(model="copter:1", capacity=None, instance="0"):
        """Run the real entrypoint with a selected vehicle and optional override."""
        env = {**os.environ, "VEHICLES": model, "INSTANCE": instance,
               "CAPTURE": str(capture), "FRAME_FIXTURE": str(ROOT / "copter-frame.json")}
        env.pop("BATTERY_CAPACITY_MAH", None)
        if capacity is not None:
            env["BATTERY_CAPACITY_MAH"] = capacity
        capture.unlink(missing_ok=True)
        result = subprocess.run(["bash", ROOT / "entrypoint.sh"], cwd=tmp_path,
                                env=env, text=True, capture_output=True, timeout=5)
        return result, json.loads(capture.read_text()) if capture.exists() else None

    return run


def test_default_capacity(launch):
    """The packaged default selects a finite 3.3 Ah copter frame."""
    result, data = launch()
    assert result.returncode == 0, result.stderr
    assert data["capacity"] == 3.3
    assert data["frame"] == "+"
    assert not data["args"][data["args"].index("--model") + 1].startswith("+:/")
    assert "--sysid" in data["args"] and "1" in data["args"]


def test_override_and_grouped_instances(launch):
    """All grouped copters use the converted physical capacity and existing IDs."""
    for capacity, ah in [('6600', 6.6), ('1250.5', 1.2505), ('11', 0.011)]:
        for count in [1, 3]:
            result, data = launch("copter:" + str(count), capacity, instance="4")
            assert result.returncode == 0, result.stderr
            assert data["capacity"] == ah
            assert "-I4" in data["args"]
            assert ("--auto-sysid" in data["args"]) == (count > 1)
            if count > 1:
                assert data["args"][data["args"].index("--count") + 1] == str(count)
            else:
                assert data["args"][data["args"].index("--sysid") + 1] == "5"


def test_invalid_capacity_prevents_launch(launch):
    """Reject invalid capacity before SITL starts."""
    for capacity in ['0', '10', '-1', 'nan', 'inf', 'oops', '1e100', '2147483647']:
        result, data = launch(capacity=capacity)
        assert result.returncode != 0 and data is None
        assert "BATTERY_CAPACITY_MAH" in result.stderr


def test_other_frames_unchanged(launch):
    """A copter capacity configuration must not change other vehicle frames."""
    for model, frame in [('rover', 'rover'), ('plane_fw', 'plane'), ('plane_vtol', 'quadplane')]:
        result, data = launch(model + ":1", "6600")
        assert result.returncode == 0, result.stderr
        assert data["frame"] == frame and data["capacity"] is None


def main():
    """Run the launch regressions in a temporary simulated firmware directory."""
    with TemporaryDirectory(prefix="apm-battery-") as temporary:
        run = launch(Path(temporary))
        test_default_capacity(run)
        test_override_and_grouped_instances(run)
        test_invalid_capacity_prevents_launch(run)
        test_other_frames_unchanged(run)
    print("APM battery checks passed")


if __name__ == "__main__":
    main()
