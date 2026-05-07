from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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
    teach = TeachPointStore()
    teach.load(Path(tp))
    ctx = ApplicationContext(
        config=cfg,
        teach=teach,
        teach_points_path=tp,
    )
    ctx.precheck = PreJobGate(ctx)
    return ctx


def make_robot_from_config(cfg: dict[str, Any]) -> JakaRobotController:
    robot_cfg = cfg.get("robot") or {}
    ip = str(robot_cfg.get("ip", "192.168.2.64"))
    return JakaRobotController(ip)
