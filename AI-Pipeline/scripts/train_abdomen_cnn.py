"""Run or resume the named Abdomen CNN baseline through the managed queue."""
from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.experiment_queue import load_plan, run_queue


def main() -> int:
    parser = argparse.ArgumentParser(description="Train Abdomen CNN model")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--plan", type=Path, default=Path("configs/abdomen_cnn_queue.json"))
    parser.add_argument("--only", default="abdomen-cnn-compact", help="Specific experiment name to train")
    args = parser.parse_args()

    project = args.root.resolve()
    plan_path = args.plan if args.plan.is_absolute() else project / args.plan
    plan = load_plan(plan_path)

    print(f"Executing Abdomen training for experiment: '{args.only}' ...", flush=True)
    run_queue(project, plan, only=args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
