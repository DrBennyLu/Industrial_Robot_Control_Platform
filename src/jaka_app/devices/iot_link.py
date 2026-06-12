from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IotLink(Protocol):
    """Reserved for MQTT / HTTP / cloud telemetry (implement when required)."""

    def publish_state(self, payload: dict[str, Any]) -> None:
        ...

    def subscribe_commands(self, handler: Callable[[dict[str, Any]], None]) -> None:
        ...


class NoOpIotLink:
    def publish_state(self, payload: dict[str, Any]) -> None:
        return None

    def subscribe_commands(self, handler: Callable[[dict[str, Any]], None]) -> None:
        return None
