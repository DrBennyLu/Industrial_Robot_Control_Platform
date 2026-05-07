from __future__ import annotations

from jaka_app.robot_controller import JakaRobotController

# 控制柜程序名（与 test_sdk 一致，现场可改）
PROG_HOME = "demohome"
PROG_PICK = "demopick0430"
PROG_LIFT = "demolift0506"
PROG_AFTER_PLACE = "demoafterplace0506"


def pre_action_check(
    arm: JakaRobotController,
    *,
    allow_program_busy: bool = False,
    auto_enable: bool = False,
) -> None:
    """
    下发机器人指令前的安全检查；失败抛出 RuntimeError。
    """
    ok, msg = arm.is_safe_to_move(auto_enable=auto_enable, allow_program_busy=allow_program_busy)
    if not ok:
        raise RuntimeError(msg)


def run_cabinet_program(
    arm: JakaRobotController,
    program_name: str,
    *,
    timeout_s: float = 1200.0,
    poll_s: float = 0.1,
) -> None:
    """
    不含前置安全检查：请先调用 pre_action_check。
    program_load → program_run → 启动确认 → 带监护的等待直到停止。
    """
    arm.program_load(program_name)
    arm.program_run()
    arm.confirm_cabinet_program_started()
    arm.wait_cabinet_program_complete(timeout_s=timeout_s, poll_s=poll_s)


def connect_gripper(port: str) -> GripperController:
    """连接并初始化夹爪；失败抛 RuntimeError。"""
    from DHGripper.DHController import GripperController

    g = GripperController(port=port)
    if not g.connect():
        raise RuntimeError(f"夹爪串口连接失败: {port}")
    if not g.initialize():
        raise RuntimeError("夹爪初始化超时或失败")
    return g
