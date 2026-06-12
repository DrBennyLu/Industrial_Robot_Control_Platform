from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

from jaka_app.robot_controller import JakaRobotController, find_value_by_key
from jaka_app.utils.logging_utils import add_log

_FLOW_DIR = Path(__file__).resolve().parent
_PROJECT_SRC = _FLOW_DIR.parent / "src"
if str(_PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(_PROJECT_SRC))

from ForceSensor.FS_reader import KunweiForceSensor

logger = logging.getLogger(__name__)

# 控制柜程序名（与 test_sdk 一致，现场可改）
PROG_HOME = "demohome"
PROG_VARRESET = "varreset"
# 对应1号钣金
PROG_PICK = "demopick0430"
PROG_LIFT = "demolift0506"
PROG_LIFT_1 = "demolift_1_0507"
PROG_LIFT_2 = "demolift_2_0518"
PROG_LIFT_3 = "demolift_3_0529"
PROG_LIFT_4 = "demolift_4_0529"
PROG_LIFT_5 = "demolift_5_0529"
PROG_LIFT_6 = "demolift_6_0529"
# PROG_LIFT_3 = "demolift0506_3"
PROG_AFTER_PLACE = "demoafterplace0514"
PROG_PICK_ONLY = "demopickonly0518"
PROG_FIRST_PICK = "first_pick_0513"
PROG_FIRST_PICK_PRC = "first_pick_0513prc"
# 对应2号钣金
PROG_FIRST_PICK_PRC2 = "first_pick_0528prc2"
PROG_LIFT_21 = "demolift_21_0528"
PROG_LIFT_22 = "demolift_22_0528"
PROG_LIFT_23 = "demolift_23_0601"
PROG_LIFT_24 = "demolift_24_0601"
PROG_LIFT_25 = "demolift_25_0601"
PROG_LIFT_26 = "demolift_26_0601"
PROG_AFTER_PLACE2 = "demoafterplace2_0528"
PROG_PICK_ONLY2 = "demopickonly2_0528"



# 1号钣金，料槽下标 0..n-1 对应放置子程序
LIFT_SN1_PROGRAM_BY_SLOT: list[str] = [
    PROG_LIFT_6,
    PROG_LIFT_5,
    PROG_LIFT_4,
    PROG_LIFT_3,
    PROG_LIFT_2,
    PROG_LIFT_1,
]

# 2号钣金，料槽下标 0..n-1 对应放置子程序
LIFT_SN2_PROGRAM_BY_SLOT: list[str] = [
    PROG_LIFT_26,
    PROG_LIFT_25,
    PROG_LIFT_24,
    PROG_LIFT_23,
    PROG_LIFT_22,
    PROG_LIFT_21,
]


def lift_program_for_slot(slot_index: int, SN: int) -> str:
    if slot_index < 0 or slot_index >= len(LIFT_SN1_PROGRAM_BY_SLOT) or slot_index >= len(LIFT_SN2_PROGRAM_BY_SLOT):
        raise IndexError(
            f"slot_index {slot_index} out of range"
        )
    if SN == 1:
        return LIFT_SN1_PROGRAM_BY_SLOT[slot_index]
    else:
        return LIFT_SN2_PROGRAM_BY_SLOT[slot_index]
    # return LIFT_PROGRAM_BY_SLOT[slot_index]





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
    cancel_event=None,
) -> None:
    """
    不含前置安全检查：请先调用 pre_action_check。
    program_load → program_run → 启动确认 → 带监护的等待直到停止。
    支持通过 cancel_event 中断等待。
    """
    arm.program_load(program_name)
    arm.program_run()
    arm.confirm_cabinet_program_started()
    arm.wait_cabinet_program_complete(timeout_s=timeout_s, poll_s=poll_s, cancel_event=cancel_event)


def connect_gripper(port: str) -> GripperController:
    """连接并初始化夹爪；失败抛 RuntimeError。"""
    from DHGripper.DHController import GripperController

    g = GripperController(port=port)
    if not g.connect():
        raise RuntimeError(f"夹爪串口连接失败: {port}")
    if not g.initialize():
        raise RuntimeError("夹爪初始化超时或失败")
    # 配置参数
    g.configure(force=100, speed=50)
    # print("参数配置完成")
    return g

def get_sys_val(arm: JakaRobotController, varname: str):
    var = arm.get_robot_system_var()
    val = find_value_by_key(var, varname)
    return val


def _force_sensor_settings(cfg: dict | None) -> dict[str, Any]:
    fs = (cfg or {}).get("force_sensor") or {}
    return {
        "port": str(fs.get("port") or "COM8").strip(),
        "fx_threshold_n": float(fs.get("fx_threshold_n", 45)),
        "step_mm": float(fs.get("step_mm", 1)),
        "speed_mm_s": float(fs.get("speed_mm_s", 10)),
        "filter_window_size": int(fs.get("filter_window_size", 10)),
        "send_start_command": bool(fs.get("send_start_command", False)),
        "max_steps": int(fs.get("max_steps", 500)),
        "sensor_ready_timeout_s": float(fs.get("sensor_ready_timeout_s", 10)),
        "settle_after_move_s": float(fs.get("settle_after_move_s", 0.05)),
        "motion_timeout_s": float(fs.get("motion_timeout_s", 60)),
        "over_threshold_confirm": int(fs.get("over_threshold_confirm", 2)),
    }


def _wait_force_sensor_ready(
    sensor: KunweiForceSensor,
    timeout_s: float,
    *,
    cancel_event=None,
    ctx=None,
) -> None:
    """阻塞等待力传感器产出首帧有效数据。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("力控伺服被用户取消")
        if sensor.get_latest_data(filtered=True) is not None:
            add_log("Force sensor data ready", ctx=ctx)
            return
        time.sleep(0.01)
    raise RuntimeError(f"力传感器 {timeout_s:.1f}s 内无有效数据")


def connect_force_sensor(
    cfg: dict | None,
    *,
    cancel_event=None,
    ctx=None,
) -> KunweiForceSensor:
    """连接力传感器、启动监测并等待首帧有效数据。"""
    opts = _force_sensor_settings(cfg)
    sensor = KunweiForceSensor(
        port=opts["port"],
        filter_window_size=opts["filter_window_size"],
        send_start_command=opts["send_start_command"],
    )
    add_log("Force sensor: connecting port=%s" % opts["port"], ctx=ctx)
    if not sensor.connect():
        raise RuntimeError(f"力传感器连接失败: {opts['port']}")
    if not sensor.start_monitoring():
        sensor.disconnect()
        raise RuntimeError("力传感器监测启动失败")
    _wait_force_sensor_ready(
        sensor,
        opts["sensor_ready_timeout_s"],
        cancel_event=cancel_event,
        ctx=ctx,
    )
    return sensor


def _fx_over_threshold(
    sensor: KunweiForceSensor,
    threshold_n: float,
    *,
    min_filter_samples: int,
) -> float | None:
    """
    若滤波样本不足则返回 None；否则返回当前 Fx。
    由调用方累计连续超限次数后判定停止。
    """
    if sensor.filter.count < min_filter_samples:
        return None
    data = sensor.get_latest_data(filtered=True)
    if data is None:
        return None
    return data.fx


def force_servo_control(
    arm: JakaRobotController,
    *,
    cfg: dict | None = None,
    cancel_event=None,
    ctx=None,
    sensor: KunweiForceSensor | None = None,
) -> None:
    """
    力控伺服：循环读取滤波后 Fx，|Fx| > 阈值则结束；
    否则沿 TCP x 负方向相对直线运动 step_mm（阻塞），再进入下一轮。

    参数与阈值见 config/application.yaml 中 force_sensor 段。
    sensor 已传入时复用会话连接，不在此函数内 disconnect。
    """
    opts = _force_sensor_settings(cfg)
    owns_sensor = sensor is None
    if owns_sensor:
        sensor = KunweiForceSensor(
            port=opts["port"],
            filter_window_size=opts["filter_window_size"],
            send_start_command=opts["send_start_command"],
        )
        add_log(
            "Force servo: port=%s threshold=%.1fN step=%.1fmm speed=%.1fmm/s"
            % (opts["port"], opts["fx_threshold_n"], opts["step_mm"], opts["speed_mm_s"]),
            ctx=ctx,
        )
        if not sensor.connect():
            raise RuntimeError(f"力传感器连接失败: {opts['port']}")
        if not sensor.start_monitoring():
            sensor.disconnect()
            raise RuntimeError("力传感器监测启动失败")
        _wait_force_sensor_ready(
            sensor,
            opts["sensor_ready_timeout_s"],
            cancel_event=cancel_event,
            ctx=ctx,
        )
    else:
        add_log(
            "Force servo (session sensor): threshold=%.1fN step=%.1fmm speed=%.1fmm/s"
            % (opts["fx_threshold_n"], opts["step_mm"], opts["speed_mm_s"]),
            ctx=ctx,
        )
        sensor.filter.reset()

    tcp_delta = [-opts["step_mm"], 0.0, 0.0, 0.0, 0.0, 0.0]
    steps = 0
    over_count = 0
    min_filter_samples = min(3, opts["filter_window_size"])
    confirm_need = max(1, opts["over_threshold_confirm"])

    try:
        while True:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("力控伺服被用户取消")

            fx = _fx_over_threshold(
                sensor,
                opts["fx_threshold_n"],
                min_filter_samples=min_filter_samples,
            )
            if fx is None:
                time.sleep(0.01)
                continue

            if abs(fx) > opts["fx_threshold_n"]:
                over_count += 1
                if over_count >= confirm_need:
                    add_log(
                        "Force servo stop: |Fx|=%.2fN > %.2fN after %d steps"
                        % (abs(fx), opts["fx_threshold_n"], steps),
                        ctx=ctx,
                    )
                    logger.info(
                        "力控伺服结束: |Fx|=%.2fN > %.2fN, steps=%d",
                        abs(fx),
                        opts["fx_threshold_n"],
                        steps,
                    )
                    return
            else:
                over_count = 0

            arm.linear_move_incr(tcp_delta, opts["speed_mm_s"], blocking=True)
            arm.wait_in_position(
                timeout_s=opts["motion_timeout_s"],
                cancel_event=cancel_event,
            )
            if opts["settle_after_move_s"] > 0:
                time.sleep(opts["settle_after_move_s"])

            steps += 1
            if steps >= opts["max_steps"]:
                raise RuntimeError(
                    f"力控伺服超过最大步数 {opts['max_steps']}，未触及力阈值"
                )

    finally:
        if owns_sensor:
            sensor.stop_monitoring()
            sensor.disconnect()
        add_log("Force servo finished", ctx=ctx)
