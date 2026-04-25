#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))

    parser = argparse.ArgumentParser(description="Run Python main flow headless")
    parser.add_argument(
        "--flow",
        type=Path,
        default=ROOT / "flows" / "main_flow.py",
        help="Path to main flow Python file (must define main())",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    spec = importlib.util.spec_from_file_location("user_main_flow", args.flow)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load flow")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "main", None)
    if fn is None:
        raise SystemExit("flow module has no main()")
    fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
