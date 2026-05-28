from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jaka_app.context import ApplicationContext

logger = logging.getLogger(__name__)


class PreJobGate:
    """Aggregate safety / readiness checks before motion or job start."""

    def __init__(self, ctx: ApplicationContext) -> None:
        self._ctx = ctx

    def assert_all(self, *, require_program_idle: bool = True) -> None:
        ctx = self._ctx
        ctx.io.assert_permit()
        ctx.line.assert_ready()
        ctx.vision.assert_camera_ok()
        if not ctx.plc.is_ready():
            raise RuntimeError("PLC reports not ready (replace NoOpPlcClient when wired).")
        robot = ctx.robot
        if robot is None:
            raise RuntimeError("Robot is not connected.")
        snap = robot.snapshot_status()
        if snap.emergency_stop == 1 or snap.estoped == 1:
            raise RuntimeError("Emergency stop is active.")
        power_vals = [v for v in (snap.powered_on, snap.power_on_state) if v is not None]
        if power_vals and max(int(v) for v in power_vals) == 0:
            raise RuntimeError("Robot is not powered on.")
        enable_vals = [v for v in (snap.enabled, snap.servo_enabled) if v is not None]
        if enable_vals and max(int(v) for v in enable_vals) == 0:
            raise RuntimeError("Robot servo is not enabled.")
        if snap.errcode not in (None, 0):
            raise RuntimeError(f"Robot fault errcode={snap.errcode}")
        if snap.protective_stop == 1:
            raise RuntimeError("Protective stop / collision state; recover manually before continuing.")
        if require_program_idle and snap.program_state == 1:
            raise RuntimeError("A cabinet program is still running; pause/abort before starting a new job from Python.")
