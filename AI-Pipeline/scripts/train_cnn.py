"""Run or resume the named Heart CNN baseline through the managed queue."""
from __future__ import annotations

from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.experiment_queue import load_plan, run_queue


if __name__ == "__main__":
    project = Path(__file__).resolve().parents[1]
    plan = load_plan(project / "configs/heart_cnn_queue.json")
    run_queue(project, plan, only="cnn-compact")
