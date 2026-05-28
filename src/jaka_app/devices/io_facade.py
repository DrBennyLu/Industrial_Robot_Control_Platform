from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IODeviceFacade(Protocol):
    """Reserved for digital IO / safety interlocks (implement when wiring is known)."""

    def assert_permit(self) -> None:
        """Raise RuntimeError if motion or cycle must not proceed."""
        ...


class NoOpIODeviceFacade:
    def assert_permit(self) -> None:
        return None
