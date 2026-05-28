#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from jaka_app.gui.main_window import run_hmi

    p = argparse.ArgumentParser(description="JAKA PyQt5 HMI")
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "application.yaml",
        help="Path to application.yaml",
    )
    p.add_argument("--flow", type=Path, default=None, help="Default main flow .py path")
    args = p.parse_args()
    return run_hmi(args.config, flow_path=args.flow)


if __name__ == "__main__":
    raise SystemExit(main())
