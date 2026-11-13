"""Acquire pinned patient-disjoint SPRSound 2022 TRAIN data only."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.sprsound import acquire_training

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    report = acquire_training(args.root)
    print({key: value for key, value in report.items() if key != "files"})
