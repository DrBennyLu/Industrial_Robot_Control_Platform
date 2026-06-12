from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


def add_log(content: str, ctx: Any = None) -> None:
    """Emit one log line to GUI sink when available, fallback to stdout."""
    text = str(content)
    sink: Callable[[str], None] | None = getattr(ctx, "log_sink", None) if ctx is not None else None
    if callable(sink):
        sink(text)
        return
    stamped = f"[{datetime.now().isoformat(timespec='seconds')}] {text}"
    print(stamped)
