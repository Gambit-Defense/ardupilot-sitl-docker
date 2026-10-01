#!/usr/bin/env python3
"""Exercise battery exhaustion in a live Copter or Rover SITL process over MAVLink."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

from pymavlink import mavutil


def command(link, command_id, *parameters):
    """Send a command and require its successful acknowledgement."""
    values = list(parameters) + [0] * (7 - len(parameters))
    link.mav.command_long_send(1, 1, command_id, 0, *values)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        ack = link.recv_match(type="COMMAND_ACK", blocking=True, timeout=1)
        if ack and ack.command == command_id:
            assert ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED, "%s: %s" % (
                ack, link.messages.get("STATUSTEXT"))
            return
    raise AssertionError("No acknowledgement for command %s" % command_id)


def observe(link, seconds):
    """Collect physical altitude and continuing telemetry for a wall-clock interval."""
    samples = []
    heartbeats = 0
    battery = None
    speed = 0.0
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        message = link.recv_match(blocking=True, timeout=0.2)
        if message is None:
            continue
        if message.get_type() == "GLOBAL_POSITION_INT":
            samples.append((message.time_boot_ms, message.relative_alt / 1000.0))
            speed = (message.vx ** 2 + message.vy ** 2) ** 0.5 / 100.0
        elif message.get_type() == "HEARTBEAT":
            heartbeats += 1
        elif message.get_type() == "BATTERY_STATUS":
            battery = message.battery_remaining
        elif message.get_type() == "STATUSTEXT":
            print(message.text, flush=True)
    assert samples, "Position telemetry stopped"
    assert heartbeats > 0, "Heartbeat stopped"
    assert samples[-1][0] > samples[0][0], "Simulation time stopped"
    return {"altitude_start": samples[0][1], "altitude_end": samples[-1][1],
            "altitude_max": max(item[1] for item in samples),
            "simulation_ms": samples[-1][0] - samples[0][0],
            "heartbeats": heartbeats, "battery_remaining": battery,
            "groundspeed_end": speed}


def run(source, expect_cutoff, vehicle):
    """Command powered motion, exhaust the battery, and check motion and telemetry."""
    is_rover = vehicle == "rover"
    with tempfile.TemporaryDirectory(prefix="battery-flight-") as directory:
        work = Path(directory)
        parameters = work / "battery.parm"
        parameters.write_text(
            "ARMING_CHECK 0\nBATT_MONITOR 4\nBATT_CAPACITY 10000\n"
            "BATT_FS_LOW_ACT 0\nBATT_FS_CRT_ACT 0\n"
            "FS_THR_ENABLE 0\nFS_GCS_ENABLE 0\nRC_OPTIONS 0\nRC_OVERRIDE_TIME -1\n"
        )
        defaults = str(source / ("Tools/autotest/default_params/" + vehicle + ".parm")) + "," + str(parameters)
        with (work / "sitl.log").open("w") as log:
            process = subprocess.Popen(
                [str(source / ("build/sitl/bin/ardu" + vehicle)), "-w", "--model", "rover" if is_rover else "+",
                 "--speedup", "5", "--home", "47.397742,8.545594,488,0",
                 "--defaults", defaults, "--serial0", "tcp:5760"],
                cwd=work, stdout=log, stderr=subprocess.STDOUT,
            )
            link = None
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    try:
                        link = mavutil.mavlink_connection("tcp:127.0.0.1:5760")
                        break
                    except OSError:
                        if process.poll() is not None:
                            raise AssertionError("SITL exited before connecting")
                        time.sleep(0.1)
                assert link is not None, "No SITL connection"
                assert link.wait_heartbeat(timeout=10), "No heartbeat"
                link.mav.request_data_stream_send(1, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
                observe(link, 15)  # GPS/EKF initialization at 5x simulation speed.
                command(link, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 1, 0 if is_rover else 4)
                command(link, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1, 21196)
                if is_rover:
                    link.mav.rc_channels_override_send(1, 1, 1500, 1500, 1800, 1500, 0, 0, 0, 0)
                else:
                    command(link, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 10)
                before = observe(link, 8)
                assert before["groundspeed_end" if is_rover else "altitude_end"] > (2 if is_rover else 8), before
                # Set charge accounting to exactly empty, leaving failsafe actions disabled.
                command(link, mavutil.mavlink.MAV_CMD_BATTERY_RESET, 1, 0)
                after = observe(link, 4)
                assert after["battery_remaining"] == 0, after
                metric = after["groundspeed_end" if is_rover else "altitude_end"]
                if expect_cutoff:
                    assert metric < 1, after
                else:
                    assert metric > (2 if is_rover else 8), after
                result = {"vehicle": vehicle, "expect_cutoff": expect_cutoff, "before": before, "after": after}
                if is_rover and expect_cutoff:
                    command(link, mavutil.mavlink.MAV_CMD_BATTERY_RESET, 1, 100)
                    link.mav.rc_channels_override_send(1, 1, 1500, 1500, 2000, 1500, 0, 0, 0, 0)
                    result["after_monitor_reset"] = observe(link, 3)
                    assert result["after_monitor_reset"]["groundspeed_end"] > 2, result
                print(json.dumps(result, indent=2), flush=True)
            except BaseException:
                print((work / "sitl.log").read_text()[-6000:], flush=True)
                raise
            finally:
                if link is not None:
                    link.close()
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    """Parse the source checkout and expected simulator behavior."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/home/atlas/ardupilot"))
    parser.add_argument("--expect-cutoff", action="store_true")
    parser.add_argument("--vehicle", choices=("copter", "rover"), default="copter")
    args = parser.parse_args()
    run(args.source, args.expect_cutoff, args.vehicle)


if __name__ == "__main__":
    main()
