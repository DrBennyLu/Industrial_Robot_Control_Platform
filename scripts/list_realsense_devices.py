#!/usr/bin/env python3
"""List connected Intel RealSense devices (name + serial_number)."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import pyrealsense2 as rs
    except ImportError:
        print("pyrealsense2 is not installed. Run: pip install pyrealsense2", file=sys.stderr)
        return 1

    ctx = rs.context()
    devices = ctx.query_devices()
    if len(devices) == 0:
        print("No RealSense devices found.")
        return 0

    print("Connected RealSense devices:")
    for i, dev in enumerate(devices):
        name = dev.get_info(rs.camera_info.name)
        serial = dev.get_info(rs.camera_info.serial_number)
        print("  [%d] name=%r serial_number=%r" % (i, name, serial))
    print("\nCopy serial_number values into config/application.yaml:")
    print("  data_collection.cameras.box_image.serial_number")
    print("  data_collection.cameras.wrist_image.serial_number")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
