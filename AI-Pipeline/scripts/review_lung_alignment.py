"""Create sampled development audio/annotation review; never train or open test labels."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.lung_alignment import review_alignment

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--audit", type=Path, default=Path("data/processed/lung/audit.json"))
    parser.add_argument("--root", type=Path, default=Path("data/external/hf-lung-v1/extracted"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recording-id", action="append", help="Repeat for specific cached development IDs")
    args = parser.parse_args()
    report = review_alignment(args.cache, args.audit, args.root, args.output, recording_ids=args.recording_id)
    print(f"Saved {args.output}/review.html; human listening review remains required.")
    if not report["source_cache_agreement"]:
        raise SystemExit("Source/cache mismatch found: inspect report.json before training")
