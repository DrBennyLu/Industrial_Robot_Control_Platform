from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_application_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("application config root must be a mapping")
    return data


def env_password(cfg: dict[str, Any]) -> str:
    robot = cfg.get("robot") or {}
    env_name = robot.get("password_env") or ""
    if not env_name:
        return str(robot.get("password") or "")
    return os.environ.get(env_name, "")
