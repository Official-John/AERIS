"""Adapter between AERIS and the stand-in autopilot.

This is the only file that knows both sides. It builds the SensorFrame AERIS reads
and turns AERIS Commands into autopilot API calls. A future PX4 adapter
(adapters/px4_ros2.py) would do the same job with ROS 2 topics and PX4 modes,
and the AERIS core would not change.
"""
from ..core.types import SensorFrame


def build_frame(t, msgs, autopilot, motor_outputs):
    tel = autopilot.telemetry()
    gps = msgs.get("gps")
    return SensorFrame(
        t=t,
        imu=msgs.get("imu"),
        gps_pos=gps["pos"] if gps else None,
        gps_vel=gps["vel"] if gps else None,
        baro=msgs.get("baro"),
        mag=msgs.get("mag"),
        vision=msgs.get("vision"),
        battery=msgs.get("battery"),
        motor_outputs=tuple(motor_outputs),
        est_pos=tel["pos"], est_vel=tel["vel"], est_yaw=tel["yaw"],
        accel_sp=tel["accel_sp"], mode=tel["mode"], gps_test_ratio=tel["gps_test_ratio"],
        remaining_wps=tuple(tel["remaining_wps"]), armed=tel["armed"],
    )


def apply_commands(commands, autopilot):
    """Returns a list of (command, accepted) for the log."""
    results = []
    for c in commands:
        ok = True
        if c.kind == "set_mode":
            ok = autopilot.set_mode(c.value, c.reason)
        elif c.kind == "exclude_sensor":
            autopilot.exclude_sensor(c.value)
        elif c.kind == "accel_bias":
            autopilot.set_accel_bias_correction(*c.value)
        elif c.kind == "speed_limit":
            autopilot.set_speed_limit(c.value)
        elif c.kind == "reset_position":
            autopilot.reset_horizontal_position(*c.value)
        else:
            ok = False
        results.append((c, ok))
    return results
