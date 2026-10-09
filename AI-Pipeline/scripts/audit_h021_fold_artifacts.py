"""Read-only H021 fold artifact compatibility check; never makes predictions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.murmur_inference import audit_fold_artifacts, load_h021_freeze


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, default=Path(__file__).resolve().parents[1]
                        / "analysis" / "HEART-DEVELOPMENT-FREEZE-H021")
    args = parser.parse_args()
    manifest = load_h021_freeze(args.freeze)
    folds = [audit_fold_artifacts(manifest, args.source_root, fold) for fold in range(1, 6)]
    print(json.dumps({"evaluation_folds_verified": 5, "folds": folds,
                      "deployment_status": manifest["deployment"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
