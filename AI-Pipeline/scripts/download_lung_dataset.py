"""Download verified HF_Lung_V1 archives without training."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.acquisition_lung import acquire

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path("data/external/hf-lung-v1"))
    parser.add_argument("--split", choices=["train", "test"], default="train")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    receipt = acquire(args.destination, split=args.split, extract=not args.download_only)
    print(f"Verified {len(receipt['files'])} files at revision {receipt['revision']}; no training started.")
