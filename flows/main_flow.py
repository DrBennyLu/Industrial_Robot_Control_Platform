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

import ai_flow
import flow_utils
import robot_flow
import vision_flow

# =========================
# 维护区（现场常改）
# =========================
ROBOT_IP = "192.168.1.100"
ENABLE_REAL_MOTION = True  # 调试空跑时可改为 False
SNAPSHOT_DIR = Path("logs/snapshots")
STATS_FILE = Path("logs/production_stats.json")


def main() -> None:
    """
    主流程入口（给现场技师直接编辑）。

    输入类型：
    - 无（固定读取本文件顶部配置常量）。

    输出类型：
    - None。

    说明：
    - 成功时完成一次完整生产节拍，并更新统计与快照文件。
    - 失败时记录异常统计与快照，执行回退动作后继续抛出异常。
    """
    arm = JakaRobotController(ROBOT_IP, use_grpc=True)
    stats = flow_utils.load_stats(STATS_FILE)
    cycle_start = time.time()

    try:
        arm.connect()
        print("开始生产流程...")
        flow_utils.save_snapshot(SNAPSHOT_DIR, "startup", arm, stats)

        # 1) 初始化
        robot_flow.run_init(arm, ENABLE_REAL_MOTION)

        # 2) 视觉 + AI 决策（调用子流程）
        object_type = vision_flow.detect_object_type()
        path_name = ai_flow.select_pick_place_path(object_type)
        print(f"视觉结果={object_type}, 路径={path_name}")
        flow_utils.save_snapshot(SNAPSHOT_DIR, f"vision_{path_name}", arm, stats)

        # 3) 执行抓取放置与回原点（调用子流程）
        robot_flow.run_pick_and_place(arm, path_name, ENABLE_REAL_MOTION)
        robot_flow.run_home(arm, ENABLE_REAL_MOTION)

        # 成功统计
        cycle_s = flow_utils.mark_success(stats, cycle_start)
        flow_utils.save_stats(STATS_FILE, stats)
        flow_utils.save_snapshot(SNAPSHOT_DIR, "done", arm, stats)
        print(f"任务全部完成，CT={cycle_s}s，累计OK/Total={stats['cycle_ok']}/{stats['cycle_total']}")

    except Exception as e:
        # 失败统计
        flow_utils.mark_fail(stats, cycle_start, str(e))
        flow_utils.save_stats(STATS_FILE, stats)
        flow_utils.save_snapshot(SNAPSHOT_DIR, "exception", arm, stats, error_text=str(e))
        print(f"流程失败: {e}")

        try:
            robot_flow.run_recovery(arm, ENABLE_REAL_MOTION)
            flow_utils.save_snapshot(SNAPSHOT_DIR, "recovery_done", arm, stats)
        except Exception as re:
            flow_utils.save_snapshot(SNAPSHOT_DIR, "recovery_failed", arm, stats, error_text=str(re))
        raise
    finally:
        arm.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
