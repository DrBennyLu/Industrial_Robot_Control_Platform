from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LineEquipmentFacade(Protocol):
    """Reserved for conveyor / line equipment (implement when integration is known)."""

    def assert_ready(self) -> None:
        """Raise RuntimeError if line is not ready for robot motion."""
        ...

    def status_summary(self) -> str:
        """Short text for HMI status bar."""
        ...


class NoOpLineEquipmentFacade:
    def assert_ready(self) -> None:
        return None

    def status_summary(self) -> str:
        return "line: n/a"
