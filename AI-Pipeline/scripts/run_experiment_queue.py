"""Run the fixed Heart CNN experiment queue sequentially in this process.

Launch with launch_training_queue.ps1 to keep it independent of Codex.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.experiment_queue import (
    active_training_processes, backfill_active, backfill_completed,
    find_experiment, load_plan, run_queue, status_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--plan", type=Path, default=Path("configs/heart_cnn_queue.json"))
    parser.add_argument("--only", help="Run one named entry from the plan")
    parser.add_argument("--dry-run", action="store_true", help="Inspect queue without training")
    parser.add_argument("--migrate-only", action="store_true", help="Backfill legacy status without training")
    args = parser.parse_args()
    root = args.root.resolve()
    plan_path = args.plan if args.plan.is_absolute() else root / args.plan
    try:
        plan = load_plan(plan_path)
        if args.dry_run or args.migrate_only:
            if args.migrate_only:
                processes = active_training_processes()
                for item in plan["experiments"]:
                    directory = find_experiment(root, item["name"])
                    if directory is None:
                        continue
                    backfill_completed(directory)
                    owner = next((p for p in processes if p["name"] == item["name"]), None)
                    if owner and not (directory / "metrics.json").exists():
                        backfill_active(directory, owner["pid"])
            for row in status_rows(root, plan):
                if args.only is None or row["name"] == args.only:
                    print(f"{row['name']}: {row['status']} ({row['experiment_id'] or '-'})")
            return 0
        run_queue(root, plan, only=args.only)  # Prints each outcome to the detached log.
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        parser.exit(2, f"Queue error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
