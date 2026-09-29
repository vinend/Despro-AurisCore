"""Run participant-exclusive cross-validation for the spectrogram CNN."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.config import load_config
from auriscore.cross_validation import cross_validate_cnn
from auriscore.io import read_table
from auriscore.pipeline import stamp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--config", type=Path, default=Path("configs/heart_spectrogram_cnn.yaml")
    )
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        config = load_config(root / args.config)
        stamp(root, config, "segments", verify=True)
        result = cross_validate_cnn(
            read_table(root / "data/processed/segments.csv"), config, root
        )
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"Cannot cross-validate CNN: {exc}\n")

