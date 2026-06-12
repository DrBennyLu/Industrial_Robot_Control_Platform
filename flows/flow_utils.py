from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def default_stats() -> dict:
    """
    生成默认生产统计结构。

    输入类型：
    - 无。

    输出类型：
    - dict：包含总数、OK/NG、CT、良率、最后错误等字段。
    """
    return {
        "cycle_total": 0,
        "cycle_ok": 0,
        "cycle_ng": 0,
        "last_cycle_s": 0.0,
        "avg_cycle_s": 0.0,
        "best_cycle_s": 0.0,
        "yield_rate": 0.0,
        "last_error": "",
        "last_update": "",
    }


def load_stats(stats_file: Path) -> dict:
    """
    从磁盘读取生产统计；文件不存在或损坏时返回默认值。

    输入类型：
    - stats_file: Path，统计 JSON 文件路径。

    输出类型：
    - dict：生产统计数据。
    """
    if not stats_file.exists():
        return default_stats()
    try:
        return json.loads(stats_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("统计文件损坏，已重置。")
        return default_stats()


def save_stats(stats_file: Path, stats: dict) -> None:
    """
    将生产统计写入磁盘，并刷新最后更新时间。

    输入类型：
    - stats_file: Path，统计 JSON 文件路径。
    - stats: dict，待保存的统计数据。

    输出类型：
    - None。
    """
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats["last_update"] = datetime.now().isoformat(timespec="seconds")
    stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def save_snapshot(snapshot_dir: Path, tag: str, arm, stats: dict, error_text: str = "") -> None:
    """
    保存关键状态快照，便于追溯问题。

    输入类型：
    - snapshot_dir: Path，快照目录。
    - tag: str，快照标签（如 startup/done/exception）。
    - arm: JakaRobotController | None，机器人控制器实例。
    - stats: dict，当前统计数据。
    - error_text: str，异常说明，默认空字符串。

    输出类型：
    - None。
    """
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    file_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{tag}.json"
    target = snapshot_dir / file_name
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "stats": stats,
        "error": error_text,
        "robot_status": arm.get_detailed_status() if arm else None,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_job(arm, job_name: str, enable_real_motion: bool) -> None:
    """
    执行一个控制柜子程序（支持空跑）。

    输入类型：
    - arm: JakaRobotController，机器人控制器实例。
    - job_name: str，控制柜子程序名。
    - enable_real_motion: bool，True=真实执行，False=仅打印空跑信息。

    输出类型：
    - None。

    异常：
    - RuntimeError：作业执行失败时抛出。
    """
    if not enable_real_motion:
        print(f"[空跑] {job_name}")
        return
    ok = arm.run_remote_job_robust(job_name, wait_until_done=True, timeout_s=1200.0, poll_s=0.5)
    if not ok:
        raise RuntimeError(f"子程序执行失败: {job_name}")


def mark_success(stats: dict, cycle_start: float) -> float:
    """
    更新一次成功节拍的统计信息。

    输入类型：
    - stats: dict，当前统计数据。
    - cycle_start: float，本节拍开始时间戳（time.time()）。

    输出类型：
    - float：本次节拍 CT（秒）。
    """
    cycle_s = round(time.time() - cycle_start, 3)
    stats["cycle_total"] += 1
    stats["cycle_ok"] += 1
    stats["last_cycle_s"] = cycle_s
    if stats["best_cycle_s"] == 0.0 or cycle_s < stats["best_cycle_s"]:
        stats["best_cycle_s"] = cycle_s
    stats["avg_cycle_s"] = round(((stats["avg_cycle_s"] * (stats["cycle_total"] - 1)) + cycle_s) / stats["cycle_total"], 3)
    stats["yield_rate"] = round((stats["cycle_ok"] / stats["cycle_total"]) * 100.0, 2)
    stats["last_error"] = ""
    return cycle_s


def mark_fail(stats: dict, cycle_start: float, error_text: str) -> float:
    """
    更新一次失败节拍的统计信息。

    输入类型：
    - stats: dict，当前统计数据。
    - cycle_start: float，本节拍开始时间戳（time.time()）。
    - error_text: str，失败原因文本。

    输出类型：
    - float：本次节拍 CT（秒）。
    """
    cycle_s = round(time.time() - cycle_start, 3)
    stats["cycle_total"] += 1
    stats["cycle_ng"] += 1
    stats["last_cycle_s"] = cycle_s
    stats["yield_rate"] = round((stats["cycle_ok"] / stats["cycle_total"]) * 100.0, 2)
    stats["last_error"] = error_text
    return cycle_s
