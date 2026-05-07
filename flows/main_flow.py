from __future__ import annotations

import sys
from pathlib import Path

# 同目录子流程、项目 src（DHGripper、jaka_app）
_FLOW_DIR = Path(__file__).resolve().parent
_PROJECT_SRC = _FLOW_DIR.parent / "src"
for _p in (_FLOW_DIR, _PROJECT_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from jaka_app.robot_controller import JakaRobotController

import robot_flow

# =========================
# 维护区（现场常改）
# =========================
ROBOT_IP = "169.254.5.10"
GRIPPER_PORT = "COM7"

# 柜内程序名见 robot_flow（PROG_HOME 等）


def main() -> None:
    arm = JakaRobotController(ROBOT_IP)
    gripper = None
    try:
        arm.connect()

        gripper = robot_flow.connect_gripper(GRIPPER_PORT)
        gripper.open()

        robot_flow.pre_action_check(arm)
        robot_flow.run_cabinet_program(arm, robot_flow.PROG_HOME)

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
    finally:
        if gripper is not None and gripper.is_connected:
            gripper.disconnect()
        arm.disconnect()


if __name__ == "__main__":
    main()
