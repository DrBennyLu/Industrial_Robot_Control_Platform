#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    flows_dir = ROOT / "flows"
    src_dir = ROOT / "src"
    for p in (flows_dir, src_dir):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)

    parser = argparse.ArgumentParser(description="Run Python main flow headless")
    parser.add_argument(
        "--flow",
        type=Path,
        default=ROOT / "flows" / "main_flow.py",
        help="Path to main flow Python file (must define main())",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from jaka_app.config_loader import load_application_config
    from jaka_app.context import build_application_context

    import init_flow

    cfg = load_application_config(ROOT / "config" / "application.yaml")
    ctx = build_application_context(cfg)

    spec = importlib.util.spec_from_file_location("user_main_flow", args.flow)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load flow")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "main", None)
    if fn is None:
        raise SystemExit("flow module has no main()")

    try:
        init_flow.init_session(ctx)
        fn(ctx=ctx)
    finally:
        init_flow.teardown_session(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
