"""Inspect development labels, masks, weights and saved scores without training."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.lung_diagnostics import diagnose


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--audit", type=Path, default=Path("data/processed/lung/audit.json"))
    parser.add_argument("--experiment", type=Path, help="Existing development experiment; never a final/holdout candidate")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Never overwrite diagnostic evidence")
    report = diagnose(args.cache, args.audit, experiment=args.experiment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, allow_nan=False)
    print(f"Diagnostics saved to {args.output}; no training or official-test opening.")
