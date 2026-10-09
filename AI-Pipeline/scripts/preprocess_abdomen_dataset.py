"""Preprocess and segment Bowel Sounds audio with event annotations."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

import _bootstrap  # noqa: F401
from auriscore.config import load_config
from auriscore.dataset_abdomen import segment_abdomen_with_annotations
from auriscore.pipeline import stamp

LOG = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess and segment Abdomen audio recordings")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=Path("configs/abdomen_cnn.yaml"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = load_config(config_path)

    manifest_path = root / "metadata" / "abdomen_dataset_manifest.csv"
    if not manifest_path.exists():
        manifest_path = root / "metadata" / "dataset_manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found at {manifest_path}. Run python scripts/build_abdomen_manifest.py first."
        )

    manifest = pd.read_csv(manifest_path)
    LOG.info("Preprocessing %d recordings from manifest", len(manifest))
    segments = segment_abdomen_with_annotations(root, config, manifest)
    stamp(root, config, "segments")
    LOG.info("Abdomen preprocessing complete: %d segments generated", len(segments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
