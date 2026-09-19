"""Screen one WAV offline using a trusted local model artifact."""
import argparse
import json
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.inference import screen

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model", type=Path, default=Path("artifacts/models/heart_svm.joblib"))
    args = parser.parse_args()
    try:
        print(json.dumps(screen(args.audio, args.model), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot screen: {exc}. Train the baseline first.\n")
