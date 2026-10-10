"""Research-only WAV onset/offset localization with a completed Lung checkpoint."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.lung_localization import localize_wav

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--fold", type=int, default=0)
    parser.add_argument("--minimum-s", type=float, default=0)
    parser.add_argument("--merge-gap-s", type=float, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.experiment.resolve() in args.output.resolve().parents:
        parser.error("Use a new output outside the immutable experiment directory")
    result = localize_wav(args.experiment, args.wav, fold=args.fold,
                          minimum_s=args.minimum_s, merge_gap_s=args.merge_gap_s)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, allow_nan=False)
    print(f"Research localization saved to {args.output}; no training or live activation.")
