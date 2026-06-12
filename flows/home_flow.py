from __future__ import annotations

import sys
from pathlib import Path

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


def load_robot_ip() -> str:
    cfg = load_application_config(_APPLICATION_YAML)
    robot = cfg.get("robot") or {}
    ip = str(robot.get("ip") or "").strip()
    if not ip:
        raise ValueError(f"robot.ip is missing or empty in {_APPLICATION_YAML}")
    return ip


def run_home(arm: JakaRobotController) -> None:
    robot_flow.pre_action_check(arm)
    robot_flow.run_cabinet_program(arm, robot_flow.PROG_HOME)


def main() -> None:
    robot_ip = load_robot_ip()
    arm = JakaRobotController(robot_ip)
    try:
        arm.connect()
        run_home(arm)
    finally:
        arm.disconnect()


if __name__ == "__main__":
    main()
