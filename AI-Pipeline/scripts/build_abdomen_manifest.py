"""Build, split, and validate the Bowel Sounds dataset manifest."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.analysis import analyze_dataset
from auriscore.config import load_config
from auriscore.dataset_abdomen import assign_abdomen_splits, build_abdomen_manifest

LOG = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and split Abdomen dataset manifest")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=Path("configs/abdomen_cnn.yaml"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = load_config(config_path)

    dataset_dir = root / config.get("dataset_dir", "data/external/bowel-sounds")
    manifest_path = root / "metadata" / "dataset_manifest.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    LOG.info("Scanning dataset under %s", dataset_dir)
    frame = build_abdomen_manifest(root, dataset_dir)
    analyze_dataset(root, frame)

    frame = assign_abdomen_splits(frame, config)
    frame.to_csv(manifest_path, index=False)
    analyze_dataset(root, frame)

    LOG.info(
        "Saved Abdomen manifest with %d recordings across %d subjects to %s",
        len(frame), frame["subject_group"].nunique(), manifest_path
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
