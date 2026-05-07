from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PlcClient(Protocol):
    """Reserved for PLC (Modbus / S7 / OPC UA / etc.)."""

    def is_ready(self) -> bool:
        ...

    def ping(self) -> bool:
        """Optional connectivity check."""
        ...


class NoOpPlcClient:
    def is_ready(self) -> bool:
        return True

    def ping(self) -> bool:
        return True
