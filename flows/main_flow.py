from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from jaka_app.robot_controller import JakaRobotController

# 允许直接运行本文件时导入同目录子流程
FLOW_DIR = Path(__file__).resolve().parent
if str(FLOW_DIR) not in sys.path:
    sys.path.insert(0, str(FLOW_DIR))

# 项目 src 根目录（用于 DHGripper 等未单独打包的模块）
PROJECT_SRC = Path(__file__).resolve().parent.parent / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from DHGripper.DHController import GripperController

import ai_flow
import flow_utils
import robot_flow
import vision_flow

# =========================
# 维护区（现场常改）
# =========================
ROBOT_IP = "192.168.1.100"
ENABLE_REAL_MOTION = False  # 真机调试时改为 True；仅连接检查时可保持 False

SNAPSHOT_DIR = Path("logs/snapshots")
STATS_FILE = Path("logs/production_stats.json")

# 夹爪（Modbus RTU 串口）——现场按实际修改
GRIPPER_SERIAL_PORT = "COM3"  # Linux 示例: "/dev/ttyUSB0"
GRIPPER_FORCE_PCT = 50
GRIPPER_SPEED_PCT = 50

# =========================
# 真机分步调试（建议一次只多开一个 True，自下而上累积验证）
#
# 用法 A：改布尔开关（推荐，不易留下半截注释导致语法错误）
# 用法 B：在 main() 里整段注释掉某个「阶段 N」代码块，效果相同
# =========================

# 阶段 1：仅登录控制器并打印状态，随后退出（不占机器人程序、不动作）
STAGE_CONNECT_ONLY = True

# 阶段 2：在阶段 1 通过后，打开此项验证夹爪串口（依赖 ENABLE_REAL_MOTION）
STAGE_GRIPPER = False

# 阶段 3：关节空间微动（请先确认干涉与安全空间；delta=0 则只读当前关节角不移动）
STAGE_SIMPLE_MOTION = False
SIMPLE_MOTION_JOINT_INDEX = 0  # 0..6，按现场坐标系选择一根轴做极小增量
SIMPLE_MOTION_DELTA_RAD = 0.0  # 例如 0.02（约 1°）；非 0 时才真实运动
SIMPLE_MOTION_SPEED_RAD_S = 0.2

# 阶段 4：调用单个控制柜子程序并等待结束（改为你现场已有的短程序更安全）
STAGE_SUBROUTINE = False
SUBROUTINE_JOB_NAME = robot_flow.JOB_HOME  # 例如 GO_HOME / INIT_ROBOT 等

# 阶段 5：完整节拍（初始化子程序 → 夹爪 → 视觉 + 抓取放置 + 回零 + 统计）
STAGE_FULL_PRODUCTION_CYCLE = False


def _connect_gripper_or_raise(port: str, force_pct: int, speed_pct: int) -> GripperController:
    g = GripperController(port=port)
    if not g.connect():
        raise RuntimeError(f"夹爪串口连接失败: {port}")
    print("夹爪连接成功，正在初始化…")
    if not g.initialize():
        raise RuntimeError("夹爪初始化超时或失败")
    g.configure(force=force_pct, speed=speed_pct)
    print("夹爪初始化完成")
    return g


def _maybe_simple_motion_probe(
    arm: JakaRobotController,
    enable_real: bool,
    joint_index: int,
    delta_rad: float,
    speed_rad_s: float,
) -> None:
    """读当前关节角；若 delta_rad!=0 且 enable_real，则做单轴增量运动。"""
    q = arm.get_actual_joint_position()
    print(f"[调试-简单运动] 当前关节(rad): {[round(x, 4) for x in q]}")
    if not enable_real:
        print("[调试-简单运动] ENABLE_REAL_MOTION=False，跳过真实运动")
        return
    if delta_rad == 0.0:
        print("[调试-简单运动] SIMPLE_MOTION_DELTA_RAD=0，跳过移动（仅验证读轴）")
        return
    if not (0 <= joint_index < len(q)):
        raise ValueError(f"SIMPLE_MOTION_JOINT_INDEX 无效: {joint_index}")
    q_target = list(q)
    q_target[joint_index] += delta_rad
    print(
        f"[调试-简单运动] J{joint_index + 1} 增量 {delta_rad} rad，速度 {speed_rad_s} rad/s "
        "(确认无障碍后再试)"
    )
    arm.joint_move_abs(q_target, speed_rad_s, blocking=True)
    print("[调试-简单运动] 单步关节运动完成")


def main() -> None:
    """
    主流程入口（给现场技师直接编辑）。

    输入类型：
    - 无（固定读取本文件顶部配置常量）。

    输出类型：
    - None。

    说明：
    - 通过顶部 STAGE_* 开关分步真机验证；全开 STAGE_FULL_PRODUCTION_CYCLE 时行为接近原完整节拍。
    - 成功时按阶段更新统计与快照；失败时记录异常并尝试回退。
    """
    arm = JakaRobotController(ROBOT_IP, use_grpc=True)
    stats = flow_utils.load_stats(STATS_FILE)
    cycle_start = time.time()
    gripper: GripperController | None = None

    downstream_enabled = any(
        (
            STAGE_GRIPPER,
            STAGE_SIMPLE_MOTION,
            STAGE_SUBROUTINE,
            STAGE_FULL_PRODUCTION_CYCLE,
        )
    )

    try:
        # ---------- 阶段 0：连接 ----------
        arm.connect()
        print("控制器已连接")
        flow_utils.save_snapshot(SNAPSHOT_DIR, "startup", arm, stats)
        detail = arm.get_detailed_status()
        print(f"机器人状态摘要: {detail}")

        if STAGE_CONNECT_ONLY and not downstream_enabled:
            print(
                "分步调试：仅执行连接检查，结束。"
                "下一步请将 STAGE_CONNECT_ONLY=False 并打开 STAGE_GRIPPER 等开关。"
            )
            return

        if STAGE_CONNECT_ONLY and downstream_enabled:
            print("提示：已开启后续阶段，将继续执行；若只想测连接，请把其余 STAGE_* 保持 False。")

        # ---------- 阶段 2：夹爪 ----------
        if STAGE_GRIPPER:
            if not ENABLE_REAL_MOTION:
                print("[空跑] STAGE_GRIPPER 已开但 ENABLE_REAL_MOTION=False，跳过夹爪")
            else:
                gripper = _connect_gripper_or_raise(
                    GRIPPER_SERIAL_PORT, GRIPPER_FORCE_PCT, GRIPPER_SPEED_PCT
                )

        # ---------- 阶段 3：简单运动 ----------
        if STAGE_SIMPLE_MOTION:
            _maybe_simple_motion_probe(
                arm,
                ENABLE_REAL_MOTION,
                SIMPLE_MOTION_JOINT_INDEX,
                SIMPLE_MOTION_DELTA_RAD,
                SIMPLE_MOTION_SPEED_RAD_S,
            )

        # ---------- 阶段 4：单子程序 ----------
        if STAGE_SUBROUTINE:
            print(f"[调试-子程序] 调用 {SUBROUTINE_JOB_NAME} …")
            flow_utils.run_job(arm, SUBROUTINE_JOB_NAME, ENABLE_REAL_MOTION)

        # ---------- 阶段 5：完整产线节拍 ----------
        if STAGE_FULL_PRODUCTION_CYCLE:
            robot_flow.run_init(arm, ENABLE_REAL_MOTION)

            if ENABLE_REAL_MOTION and gripper is None:
                gripper = _connect_gripper_or_raise(
                    GRIPPER_SERIAL_PORT, GRIPPER_FORCE_PCT, GRIPPER_SPEED_PCT
                )
            elif not ENABLE_REAL_MOTION:
                print("[空跑] 完整节拍：跳过夹爪串口")

            object_type = vision_flow.detect_object_type()
            path_name = ai_flow.select_pick_place_path(object_type)
            print(f"视觉结果={object_type}, 路径={path_name}")
            flow_utils.save_snapshot(SNAPSHOT_DIR, f"vision_{path_name}", arm, stats)

            robot_flow.run_pick_and_place(arm, path_name, ENABLE_REAL_MOTION, gripper=gripper)
            robot_flow.run_home(arm, ENABLE_REAL_MOTION)

            cycle_s = flow_utils.mark_success(stats, cycle_start)
            flow_utils.save_stats(STATS_FILE, stats)
            flow_utils.save_snapshot(SNAPSHOT_DIR, "done", arm, stats)
            print(f"任务全部完成，CT={cycle_s}s，累计OK/Total={stats['cycle_ok']}/{stats['cycle_total']}")
        elif downstream_enabled and not STAGE_FULL_PRODUCTION_CYCLE:
            print("分步调试：后续阶段未包含完整节拍，本次不更新产量统计。")

    except Exception as e:
        flow_utils.mark_fail(stats, cycle_start, str(e))
        flow_utils.save_stats(STATS_FILE, stats)
        flow_utils.save_snapshot(SNAPSHOT_DIR, "exception", arm, stats, error_text=str(e))
        print(f"流程失败: {e}")

        try:
            if ENABLE_REAL_MOTION:
                robot_flow.run_recovery(arm, ENABLE_REAL_MOTION)
                flow_utils.save_snapshot(SNAPSHOT_DIR, "recovery_done", arm, stats)
        except Exception as re:
            flow_utils.save_snapshot(SNAPSHOT_DIR, "recovery_failed", arm, stats, error_text=str(re))
        raise
    finally:
        if gripper is not None and gripper.is_connected:
            gripper.disconnect()
        arm.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
