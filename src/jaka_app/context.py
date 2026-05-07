from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from jaka_app.devices import (
    IODeviceFacade,
    IotLink,
    LineEquipmentFacade,
    NoOpIODeviceFacade,
    NoOpIotLink,
    NoOpLineEquipmentFacade,
    NoOpPlcClient,
    NoOpVisionInspection,
    PlcClient,
    VisionInspection,
)
from jaka_app.precheck import PreJobGate
from jaka_app.robot_controller import JakaRobotController
from jaka_app.teach_points import TeachPointStore


@dataclass
class ApplicationContext:
    """Shared handles for main flow, GUI, and workers."""

    config: dict[str, Any]
    robot: JakaRobotController | None = None
    teach: TeachPointStore = field(default_factory=TeachPointStore)
    io: IODeviceFacade = field(default_factory=NoOpIODeviceFacade)
    line: LineEquipmentFacade = field(default_factory=NoOpLineEquipmentFacade)
    vision: VisionInspection = field(default_factory=NoOpVisionInspection)
    plc: PlcClient = field(default_factory=NoOpPlcClient)
    iot: IotLink = field(default_factory=NoOpIotLink)
    precheck: PreJobGate | None = None
    current_step: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event)
    teach_points_path: str = "data/teach_points.json"
    production_stats_path: str = "data/production_stats.json"
    cycle_history_path: str = "logs/cycle_history.jsonl"
    stats_lock: threading.Lock = field(default_factory=threading.Lock)
    cycle_total: int = 0
    cycle_ok: int = 0
    cycle_ng: int = 0
    cycle_start_ts: float = 0.0
    last_cycle_s: float = 0.0
    avg_cycle_s: float = 0.0
    best_cycle_s: float = 0.0
    fail_reason: str = ""
    last_error: str = ""
    run_state: str = "IDLE"
    last_update: str = ""

    def publish_iot_snapshot(self) -> None:
        """Lightweight state publish hook for future MQTT/HTTP."""
        snap = self.robot.snapshot_status() if self.robot else None
        payload = {
            "step": self.current_step,
            "errcode": getattr(snap, "errcode", None) if snap else None,
            "cycle_total": self.get_production_snapshot().get("cycle_total"),
            "cycle_ok": self.get_production_snapshot().get("cycle_ok"),
            "cycle_ng": self.get_production_snapshot().get("cycle_ng"),
        }
        self.iot.publish_state(payload)

    def cycle_begin(self) -> None:
        import time

        with self.stats_lock:
            self.cycle_start_ts = time.time()
            self.run_state = "RUNNING"
            self.fail_reason = ""
            self.last_error = ""
            self.last_update = datetime.now().isoformat(timespec="seconds")

    def cycle_success(self) -> None:
        import time

        with self.stats_lock:
            elapsed = max(0.0, time.time() - self.cycle_start_ts) if self.cycle_start_ts else 0.0
            self.cycle_total += 1
            self.cycle_ok += 1
            self.last_cycle_s = elapsed
            if self.cycle_ok == 1:
                self.avg_cycle_s = elapsed
                self.best_cycle_s = elapsed
            else:
                self.avg_cycle_s = ((self.avg_cycle_s * (self.cycle_ok - 1)) + elapsed) / self.cycle_ok
                if self.best_cycle_s <= 0 or elapsed < self.best_cycle_s:
                    self.best_cycle_s = elapsed
            self.run_state = "IDLE"
            self.last_update = datetime.now().isoformat(timespec="seconds")

    def cycle_fail(self, reason: str) -> None:
        import time

        with self.stats_lock:
            elapsed = max(0.0, time.time() - self.cycle_start_ts) if self.cycle_start_ts else 0.0
            self.cycle_total += 1
            self.cycle_ng += 1
            self.last_cycle_s = elapsed
            self.fail_reason = reason
            self.last_error = reason
            self.run_state = "FAULT"
            self.last_update = datetime.now().isoformat(timespec="seconds")

    def set_run_state(self, state: str) -> None:
        with self.stats_lock:
            self.run_state = state
            self.last_update = datetime.now().isoformat(timespec="seconds")

    def load_production_stats_from_disk(self) -> None:
        """Restore counters from JSON (restart-safe historical totals / best CT)."""
        path = Path(self.production_stats_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("生产统计文件损坏或不可读，已使用内存默认值: %s", path)
            return
        with self.stats_lock:
            self.cycle_total = int(data.get("cycle_total", 0))
            self.cycle_ok = int(data.get("cycle_ok", 0))
            self.cycle_ng = int(data.get("cycle_ng", 0))
            self.last_cycle_s = float(data.get("last_cycle_s", 0.0))
            self.avg_cycle_s = float(data.get("avg_cycle_s", 0.0))
            self.best_cycle_s = float(data.get("best_cycle_s", 0.0))
            self.fail_reason = str(data.get("fail_reason", "") or "")
            self.last_error = str(data.get("last_error", "") or "")
            lu = data.get("last_update")
            if isinstance(lu, str) and lu:
                self.last_update = lu

    def append_cycle_record(
        self,
        ok: bool,
        elapsed_s: float,
        fail_reason: str = "",
    ) -> None:
        """
        One completed main-flow invocation (single shot or one auto loop iteration).
        Updates running totals, persists aggregate JSON, optional JSONL history line.
        Does not change run_state (caller / worker owns MAIN_FLOW / IDLE / FAULT).
        """
        elapsed_s = max(0.0, float(elapsed_s))
        with self.stats_lock:
            self.cycle_total += 1
            self.last_cycle_s = elapsed_s
            self.last_update = datetime.now().isoformat(timespec="seconds")
            if ok:
                self.cycle_ok += 1
                self.fail_reason = ""
                self.last_error = ""
                if self.cycle_ok == 1:
                    self.avg_cycle_s = elapsed_s
                    self.best_cycle_s = elapsed_s
                else:
                    self.avg_cycle_s = ((self.avg_cycle_s * (self.cycle_ok - 1)) + elapsed_s) / self.cycle_ok
                    if self.best_cycle_s <= 0.0 or elapsed_s < self.best_cycle_s:
                        self.best_cycle_s = elapsed_s
            else:
                self.cycle_ng += 1
                self.fail_reason = fail_reason
                self.last_error = fail_reason

        self._persist_production_stats_to_disk()
        self._append_cycle_history_line(ok=ok, elapsed_s=elapsed_s, fail_reason=fail_reason)

    def _persist_production_stats_to_disk(self) -> None:
        path = Path(self.production_stats_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            snap = self.get_production_snapshot()
            payload = {
                "cycle_total": snap["cycle_total"],
                "cycle_ok": snap["cycle_ok"],
                "cycle_ng": snap["cycle_ng"],
                "last_cycle_s": snap["last_cycle_s"],
                "avg_cycle_s": snap["avg_cycle_s"],
                "best_cycle_s": snap["best_cycle_s"],
                "yield_rate": snap["yield_rate"],
                "fail_reason": snap["fail_reason"],
                "last_error": snap["last_error"],
                "last_update": snap["last_update"],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("写入生产统计失败 %s: %s", path, e)

    def _append_cycle_history_line(self, *, ok: bool, elapsed_s: float, fail_reason: str) -> None:
        hp = (self.cycle_history_path or "").strip()
        if not hp:
            return
        path = Path(hp)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "ok": ok,
                "elapsed_s": round(elapsed_s, 3),
                "error": fail_reason or None,
            }
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("追加节拍历史失败 %s: %s", path, e)

    def get_production_snapshot(self) -> dict[str, Any]:
        with self.stats_lock:
            total = self.cycle_total
            ok = self.cycle_ok
            ng = self.cycle_ng
            yield_rate = (ok / total * 100.0) if total > 0 else 0.0
            return {
                "cycle_total": total,
                "cycle_ok": ok,
                "cycle_ng": ng,
                "yield_rate": round(yield_rate, 2),
                "last_cycle_s": round(self.last_cycle_s, 3),
                "avg_cycle_s": round(self.avg_cycle_s, 3),
                "best_cycle_s": round(self.best_cycle_s, 3),
                "fail_reason": self.fail_reason,
                "last_error": self.last_error,
                "run_state": self.run_state,
                "last_update": self.last_update,
            }


def build_application_context(cfg: dict[str, Any]) -> ApplicationContext:
    paths = cfg.get("paths") or {}
    tp = str(paths.get("teach_points", "data/teach_points.json"))
    prod_stats = str(paths.get("production_stats", "data/production_stats.json"))
    cycle_hist = str(paths.get("cycle_history", "logs/cycle_history.jsonl"))
    teach = TeachPointStore()
    teach.load(Path(tp))
    ctx = ApplicationContext(
        config=cfg,
        teach=teach,
        teach_points_path=tp,
        production_stats_path=prod_stats,
        cycle_history_path=cycle_hist,
    )
    ctx.precheck = PreJobGate(ctx)
    ctx.load_production_stats_from_disk()
    return ctx


def make_robot_from_config(cfg: dict[str, Any]) -> JakaRobotController:
    robot_cfg = cfg.get("robot") or {}
    ip = str(robot_cfg.get("ip", "192.168.2.64"))
    return JakaRobotController(ip)
