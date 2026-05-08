from __future__ import annotations

import sys
from pathlib import Path
import time

# 同目录子流程、项目 src（DHGripper、jaka_app）
_FLOW_DIR = Path(__file__).resolve().parent
_PROJECT_SRC = _FLOW_DIR.parent / "src"
for _p in (_FLOW_DIR, _PROJECT_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from jaka_app.config_loader import load_application_config
from jaka_app.robot_controller import JakaRobotController

import robot_flow

_PROJECT_ROOT = _FLOW_DIR.parent
_APPLICATION_YAML = _PROJECT_ROOT / "config" / "application.yaml"

# 机器人 IP、夹爪串口见 config/application.yaml；柜内程序名见 robot_flow（PROG_HOME 等）

def load_from_config() -> tuple[str, str]:
    cfg = load_application_config(_APPLICATION_YAML)
    robot = cfg.get("robot") or {}
    gripper = cfg.get("gripper") or {}
    ip = str(robot.get("ip") or "").strip()
    port = str(gripper.get("port") or "").strip()
    if not ip:
        raise ValueError(f"robot.ip is missing or empty in {_APPLICATION_YAML}")
    if not port:
        raise ValueError(f"gripper.port is missing or empty in {_APPLICATION_YAML}")
    return ip, port


def main() -> None:
    robot_ip, gripper_port = load_from_config()
    arm = JakaRobotController(robot_ip)
    gripper = None
    try:
        arm.connect()

        gripper = robot_flow.connect_gripper(gripper_port)
        gripper.open()

        robot_flow.pre_action_check(arm)
        robot_flow.run_cabinet_program(arm, robot_flow.PROG_HOME)

        start_time = time.time()
        robot_flow.pre_action_check(arm)
        robot_flow.run_cabinet_program(arm, robot_flow.PROG_PICK)

        gripper.close()

        robot_flow.pre_action_check(arm)
        robot_flow.run_cabinet_program(arm, robot_flow.PROG_LIFT)

        gripper.open()

        robot_flow.pre_action_check(arm)
        robot_flow.run_cabinet_program(arm, robot_flow.PROG_AFTER_PLACE)

        robot_flow.pre_action_check(arm)
        robot_flow.run_cabinet_program(arm, robot_flow.PROG_HOME)

        end_time = time.time()
        print(f"Cycle time: {end_time - start_time} seconds")
    finally:
        if gripper is not None and gripper.is_connected:
            gripper.disconnect()
        arm.disconnect()


if __name__ == "__main__":
    main()
