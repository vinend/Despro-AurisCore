"""Print compact Heart CNN queue state without reading TensorFlow logs."""
from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.experiment_queue import load_plan, status_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--plan", type=Path, default=Path("configs/heart_cnn_queue.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    plan_path = args.plan if args.plan.is_absolute() else root / args.plan
    rows = status_rows(root, load_plan(plan_path))
    print(f"{'Experiment':38} {'Status':13} {'Epoch':>5} {'Best Val Loss':>13}")
    for row in rows:
        epoch = "-" if row["epoch"] is None else str(row["epoch"])
        loss = "-" if row["best_val_loss"] is None else f"{row['best_val_loss']:.4f}"
        print(f"{row['name']:38} {row['status']:13} {epoch:>5} {loss:>13}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
