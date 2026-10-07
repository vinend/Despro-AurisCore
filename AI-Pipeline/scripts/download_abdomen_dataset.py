"""Download the open-access Figshare Bowel Sounds dataset."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.acquisition_abdomen import acquire_abdomen
from auriscore.config import load_config

LOG = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Figshare Bowel Sounds dataset")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=Path("configs/abdomen_cnn.yaml"))
    parser.add_argument("--workers", type=int, default=4, help="Concurrent download threads")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = load_config(config_path)

    destination = root / config.get("dataset_dir", "data/external/bowel-sounds")
    LOG.info("Acquiring Abdomen dataset to %s", destination)
    result = acquire_abdomen(destination, workers=args.workers)
    LOG.info("Acquisition completed: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
