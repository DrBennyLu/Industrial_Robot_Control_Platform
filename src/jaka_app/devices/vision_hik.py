from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VisionInspection(Protocol):
    """Hikvision / MVS integration hook (NoOp until MVS is wired)."""

    def assert_camera_ok(self) -> None:
        ...

    def last_result_ok(self) -> bool:
        ...

    def inspect_infeed(self) -> bool:
        """Run or refresh infeed check; return pass/fail."""
        ...


class NoOpVisionInspection:
    def assert_camera_ok(self) -> None:
        return None

    def last_result_ok(self) -> bool:
        return True

    def inspect_infeed(self) -> bool:
        return True
