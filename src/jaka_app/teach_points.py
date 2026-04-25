from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from jaka_app.context import ApplicationContext

logger = logging.getLogger(__name__)


class TeachPointStore:
    """Named teach poses persisted as JSON (joint rad + tcp snapshot)."""

    def __init__(self) -> None:
        self._points: dict[str, dict[str, Any]] = {}

    def load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            self._points = {}
            return
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("teach_points file must be a JSON object")
        self._points = {str(k): dict(v) for k, v in data.items()}

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(self._points, f, indent=2, ensure_ascii=False)

    def add_point(
        self,
        name: str,
        joint_rad: list[float],
        tcp: list[float] | None = None,
        tool_id: int | None = None,
        user_frame_id: int | None = None,
        note: str = "",
    ) -> None:
        key = name.strip()
        if not key:
            raise ValueError("name must be non-empty")
        self._points[key] = {
            "joint_rad": [float(x) for x in joint_rad],
            "tcp": [float(x) for x in tcp] if tcp is not None else None,
            "tool_id": tool_id,
            "user_frame_id": user_frame_id,
            "note": note,
            "updated": time.time(),
        }

    def rename(self, old: str, new: str) -> None:
        if old not in self._points:
            raise KeyError(old)
        self._points[new] = self._points.pop(old)

    def delete(self, name: str) -> None:
        self._points.pop(name, None)

    def get(self, name: str) -> dict[str, Any]:
        if name not in self._points:
            raise KeyError(name)
        return dict(self._points[name])

    def list_points(self) -> list[tuple[str, dict[str, Any]]]:
        return [(k, dict(v)) for k, v in sorted(self._points.items())]


def move_to_named(
    ctx: "ApplicationContext",
    name: str,
    strategy: Literal["joint", "linear"] = "joint",
    joint_speed: float = 0.5,
    linear_speed: float = 100.0,
    require_program_idle: bool = True,
) -> None:
    """Move robot to a named teach point after precheck."""
    if ctx.precheck is None:
        raise RuntimeError("precheck not configured on context")
    ctx.precheck.assert_all(require_program_idle=require_program_idle)
    robot = ctx.robot
    if robot is None:
        raise RuntimeError("robot not connected")
    payload = ctx.teach.get(name)
    if strategy == "joint":
        joints = payload["joint_rad"]
        robot.joint_move_abs(joints, joint_speed, blocking=True)
        return
    tcp = payload.get("tcp")
    if not tcp:
        raise ValueError(f"Teach point {name!r} has no tcp pose for linear move")
    robot.linear_move_abs(tcp, linear_speed, blocking=True)


def capture_current_pose(robot: Any) -> tuple[list[float], list[float]]:  # JakaRobotController
    """Return (joint_rad, tcp) from controller."""
    j = robot.get_actual_joint_position()
    t = robot.get_actual_tcp_position()
    return j, t
