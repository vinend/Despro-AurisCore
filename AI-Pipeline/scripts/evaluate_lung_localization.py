"""Evaluate onset/offset on existing held-out development predictions only."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.lung_localization import evaluate_development_localization

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--audit", type=Path, default=Path("data/processed/lung/audit.json"))
    parser.add_argument("--fold", type=int, default=0)
    parser.add_argument("--minimum-s", type=float, default=0)
    parser.add_argument("--merge-gap-s", type=float, default=0)
    parser.add_argument("--tolerance-s", type=float, default=.1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.experiment.resolve() in args.output.resolve().parents:
        parser.error("Use a new output outside the immutable experiment directory")
    result = evaluate_development_localization(args.cache, args.audit, args.experiment, fold=args.fold,
                                               minimum_s=args.minimum_s, merge_gap_s=args.merge_gap_s,
                                               tolerance_s=args.tolerance_s)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, allow_nan=False)
    print(f"Development event evaluation saved to {args.output}; no model fitting or test opening.")
