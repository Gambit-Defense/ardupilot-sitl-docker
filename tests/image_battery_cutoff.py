#!/usr/bin/env python3
"""Check low-charge cutoff and recovery through an isolated SITL image launcher."""

import argparse
import json
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


def parameter(link, name, value=None):
    """Read or set an ArduPilot parameter and verify the returned numeric value."""
    if value is None:
        link.mav.param_request_read_send(1, 1, name.encode(), -1)
    else:
        link.mav.param_set_send(1, 1, name.encode(), value, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = link.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if result and result.param_id == name:
            if value is not None:
                assert abs(result.param_value - value) < 0.001, str(result)
            return result.param_value
    raise AssertionError("No parameter response: " + name)


def observe(link, seconds, ground_altitude=0.0):
    """Record simulator ground truth, battery load, and advancing telemetry."""
    positions = []
    truth = []
    currents = []
    heartbeats = 0
    remaining = None
    consumed_mah = None
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        message = link.recv_match(blocking=True, timeout=0.2)
        if message is None:
            continue
        kind = message.get_type()
        if kind == "GLOBAL_POSITION_INT":
            positions.append(message.time_boot_ms)
        elif kind == "SIM_STATE":
            truth.append((message.alt - ground_altitude,
                          (message.vn ** 2 + message.ve ** 2) ** 0.5))
        elif kind == "BATTERY_STATUS" and message.id == 0:
            remaining = message.battery_remaining
            consumed_mah = message.current_consumed
            currents.append(message.current_battery / 100.0)
        elif kind == "HEARTBEAT":
            heartbeats += 1
        elif kind == "STATUSTEXT":
            print(message.text, flush=True)
    assert len(positions) > 1 and positions[-1] > positions[0], "Simulation time stopped"
    assert heartbeats and truth and currents, "Required telemetry stopped"
    return {"ground_truth_height_start": truth[0][0],
            "ground_truth_height_end": truth[-1][0],
            "ground_truth_speed_end": truth[-1][1],
            "current_end_a": currents[-1], "battery_remaining": remaining,
            "consumed_mah": consumed_mah,
            "simulation_ms": positions[-1] - positions[0], "heartbeats": heartbeats}


def run(link, vehicle, expect_cutoff):
    """Cut power below 0.1% and verify restored charge permits Rover motion again."""
    assert link.wait_heartbeat(timeout=30), "No autopilot heartbeat"
    assert parameter(link, "BATT_MONITOR") == 4, "Image launcher did not enable current monitoring"
    # A large test pack keeps 0.05% positive throughout the observation window.
    capacity_mah = 1000000
    for name, value in (("ARMING_CHECK", 0), ("BATT_CAPACITY", capacity_mah),
                        ("BATT_FS_LOW_ACT", 0), ("BATT_FS_CRT_ACT", 0),
                        ("RC_OPTIONS", 0), ("RC_OVERRIDE_TIME", -1)):
        parameter(link, name, value)
    is_plane = vehicle in ("plane", "quadplane")
    if is_plane:
        parameter(link, "THR_FAILSAFE", 0)
        parameter(link, "FS_GCS_ENABL", 0)
    else:
        parameter(link, "FS_THR_ENABLE", 0)
        parameter(link, "FS_GCS_ENABLE", 0)
    for message_id in (mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
                       mavutil.mavlink.MAVLINK_MSG_ID_SIM_STATE,
                       mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS):
        command(link, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, message_id, 100000)
    ground_altitude = observe(link, 8)["ground_truth_height_end"]
    modes = link.mode_mapping()
    mode = "MANUAL" if vehicle == "rover" else "TAKEOFF" if vehicle == "plane" else "GUIDED"
    if vehicle == "quadplane":
        parameter(link, "Q_GUIDED_MODE", 1)
    if vehicle == "plane":
        parameter(link, "TKOFF_ALT", 30)
        parameter(link, "TKOFF_THR_MINACC", 0)
        parameter(link, "TKOFF_THR_MINSPD", 0)
    command(link, mavutil.mavlink.MAV_CMD_DO_SET_MODE,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, modes[mode])
    command(link, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1, 21196)
    if vehicle in ("copter", "quadplane"):
        command(link, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 15)
    else:
        link.mav.rc_channels_override_send(1, 1, 1500, 1500, 1800, 1500, 0, 0, 0, 0)
    before = observe(link, 8, ground_altitude)
    print("Before depletion: " + json.dumps(before), flush=True)
    assert before["current_end_a"] > 1, before
    if vehicle == "rover":
        assert before["ground_truth_speed_end"] > 2, before
    else:
        assert before["ground_truth_height_end"] > 8, before
    command(link, mavutil.mavlink.MAV_CMD_BATTERY_RESET, 1, 0.05)
    after = observe(link, 8, ground_altitude)
    after["remaining_pct_from_mah"] = 100 * (capacity_mah - after["consumed_mah"]) / capacity_mah
    result = {"vehicle": vehicle, "expect_cutoff": expect_cutoff,
              "before": before, "after": after}
    print(json.dumps(result, indent=2), flush=True)
    assert after["battery_remaining"] == 0, result
    if expect_cutoff:
        assert 0 < after["remaining_pct_from_mah"] < 0.1, result
        assert after["current_end_a"] < 0.1, result
        if vehicle == "rover":
            assert after["ground_truth_speed_end"] < 0.2, result
        else:
            assert after["ground_truth_height_end"] < 1, result
    else:
        assert after["current_end_a"] > 1, result
        if vehicle == "rover":
            assert after["ground_truth_speed_end"] > 2, result
        else:
            assert after["ground_truth_height_end"] > 8, result
    if vehicle == "rover":
        command(link, mavutil.mavlink.MAV_CMD_BATTERY_RESET, 1, 50)
        # The same armed process and continuing throttle must regain propulsion.
        recovered = observe(link, 8, ground_altitude)
        result["recovered"] = recovered
        print("After charge restoration: " + json.dumps(recovered), flush=True)
        assert recovered["battery_remaining"] >= 49, result
        assert recovered["current_end_a"] > 1, result
        assert recovered["ground_truth_speed_end"] > 2, result
    print("RESULT " + json.dumps(result), flush=True)


def main():
    """Connect only to the isolated image's local MAVProxy endpoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="udpin:0.0.0.0:14550")
    parser.add_argument("--vehicle", required=True, choices=("copter", "rover", "plane", "quadplane"))
    parser.add_argument("--expect-cutoff", action="store_true")
    args = parser.parse_args()
    link = mavutil.mavlink_connection(args.endpoint, source_system=255)
    try:
        run(link, args.vehicle, args.expect_cutoff)
    finally:
        link.close()


if __name__ == "__main__":
    main()
