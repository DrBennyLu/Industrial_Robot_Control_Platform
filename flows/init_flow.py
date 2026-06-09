from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

_FLOW_DIR = Path(__file__).resolve().parent
_PROJECT_SRC = _FLOW_DIR.parent / "src"
for _p in (_FLOW_DIR, _PROJECT_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from jaka_app.config_loader import load_application_config
from jaka_app.robot_controller import JakaRobotController
from jaka_app.utils.logging_utils import add_log

import robot_flow

if TYPE_CHECKING:
    from jaka_app.context import ApplicationContext

_PROJECT_ROOT = _FLOW_DIR.parent
_APPLICATION_YAML = _PROJECT_ROOT / "config" / "application.yaml"


def load_runtime_config() -> tuple[str, str, dict]:
    cfg = load_application_config(_APPLICATION_YAML)
    robot = cfg.get("robot") or {}
    gripper = cfg.get("gripper") or {}
    ip = str(robot.get("ip") or "").strip()
    port = str(gripper.get("port") or "").strip()
    if not ip:
        raise ValueError(f"robot.ip is missing or empty in {_APPLICATION_YAML}")
    if not port:
        raise ValueError(f"gripper.port is missing or empty in {_APPLICATION_YAML}")
    return ip, port, cfg


def _check_cancel(cancel_event) -> None:
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("流程被用户取消")


def init_session(ctx: ApplicationContext, *, cancel_event=None) -> None:
    """连接机器人、夹爪、力传感器并执行回零；结果写入 ctx。"""
    robot_ip, gripper_port, cfg = load_runtime_config()
    _check_cancel(cancel_event)

    arm = ctx.robot
    if arm is None or not arm.is_connected:
        add_log("Init: connecting robot %s" % robot_ip, ctx=ctx)
        arm = JakaRobotController(robot_ip)
        arm.connect()
        ctx.robot = arm
    else:
        add_log("Init: reusing robot connection %s" % arm.ip, ctx=ctx)

    gripper = ctx.gripper
    if gripper is None or not gripper.is_connected or not gripper.is_initialized:
        add_log("Init: connecting gripper %s" % gripper_port, ctx=ctx)
        gripper = robot_flow.connect_gripper(gripper_port)
        ctx.gripper = gripper
        ctx.config.setdefault("gripper", {})
        ctx.config["gripper"]["port"] = gripper_port
    else:
        add_log("Init: reusing gripper connection", ctx=ctx)

    _check_cancel(cancel_event)

    if ctx.force_sensor is None:
        add_log("Init: connecting force sensor", ctx=ctx)
        ctx.force_sensor = robot_flow.connect_force_sensor(cfg, cancel_event=cancel_event, ctx=ctx)
    else:
        add_log("Init: reusing force sensor connection", ctx=ctx)

    _check_cancel(cancel_event)

    if not gripper.open():
        raise RuntimeError("夹爪张开失败")


    robot_flow.pre_action_check(arm)
    add_log("Init: running PROG_VARREST ", ctx=ctx)
    robot_flow.run_cabinet_program(arm, robot_flow.PROG_VARRESET, cancel_event=cancel_event)
    add_log("Init: running PROG_HOME", ctx=ctx)
    robot_flow.run_cabinet_program(arm, robot_flow.PROG_HOME, cancel_event=cancel_event)


    ctx.config.setdefault("robot", {})
    ctx.config["robot"]["ip"] = robot_ip
    ctx.flow_session_ready = True
    add_log("Init: session ready", ctx=ctx)


def teardown_session(ctx: ApplicationContext) -> None:
    """断开力传感器、夹爪、机器人并清空 ctx 句柄。"""
    sensor = ctx.force_sensor
    if sensor is not None:
        try:
            sensor.stop_monitoring()
        except Exception:
            pass
        try:
            sensor.disconnect()
        except Exception:
            pass
        ctx.force_sensor = None

    gripper = ctx.gripper
    if gripper is not None:
        try:
            if gripper.is_connected:
                gripper.disconnect()
        except Exception:
            pass
        ctx.gripper = None

    arm = ctx.robot
    if arm is not None:
        try:
            arm.disconnect()
        except Exception:
            pass
        ctx.robot = None

    ctx.flow_session_ready = False
    add_log("Flow session torn down, devices disconnected.", ctx=ctx)


def main(ctx=None) -> None:
    """独立调试 init 流程。"""
    if ctx is None:
        from jaka_app.context import build_application_context

        _, _, cfg = load_runtime_config()
        ctx = build_application_context(cfg)
    try:
        init_session(ctx, cancel_event=ctx.cancel_event if ctx else None)
    except Exception:
        teardown_session(ctx)
        raise


if __name__ == "__main__":
    main()
