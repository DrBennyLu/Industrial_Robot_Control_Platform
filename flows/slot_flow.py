from __future__ import annotations

from typing import Any, Sequence

# 料槽占用：1=有料，0=空位可放置
OCCUPIED = 1
EMPTY = 0


def read_slot_io_fake(cfg: dict[str, Any]) -> list[int]:
    """假读料槽 IO：从 application.yaml 的 slot_io 数组读取（后续可换传感器）。"""
    # raw = cfg.get("slot_io")
    # if raw is None:
    #     raise ValueError("slot_io is missing in application.yaml")
    raw: list[int] = [0,0]
    # raw[0] = input("Input slot IO 0: ")
    # raw[1] = input("Input slot IO 1: ")
    return _normalize_occupancy(raw)


def _normalize_occupancy(raw: Any) -> list[int]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("slot_io must be a list of 0/1")
    out: list[int] = []
    for i, v in enumerate(raw):
        iv = int(v)
        if iv not in (OCCUPIED, EMPTY):
            raise ValueError(f"slot_io[{i}] must be 0 or 1, got {v!r}")
        out.append(iv)
    if not out:
        raise ValueError("slot_io must not be empty")
    return out


def all_slots_full(occupancy: Sequence[int]) -> bool:
    """全部为 1（有料）时返回 True。"""
    return bool(occupancy) and all(v == OCCUPIED for v in occupancy)


def find_first_empty_slot(occupancy: Sequence[int]) -> int:
    """返回第一个可放置料槽下标（值为 0）。"""
    for i, v in enumerate(occupancy):
        if v == EMPTY:
            return i
    raise RuntimeError("无空闲料槽可放置（所有料槽均为 1/有料）")
