"""Convert a WAV to CNN log-mel tensors and PNG inspection previews."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.config import load_config
from auriscore.spectrogram import export_spectrograms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--config", type=Path, default=Path("configs/heart_cnn.yaml"))
    parser.add_argument("--output", type=Path, required=True, help="New or empty export directory")
    args = parser.parse_args()
    try:
        result = export_spectrograms(args.audio, load_config(args.config), args.output)
        print(json.dumps({"status": result["status"], "windows": len(result["windows"]),
                          "output": str(args.output.resolve()), "shape": result["windows"][0]["shape"]}, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot export spectrogram: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
