"""Download the open-access Figshare Bowel Sounds dataset."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.acquisition_abdomen import acquire_abdomen

LOG = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Figshare Bowel Sounds dataset")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--destination", type=Path, default=Path("data/external/bowel-sounds"))
    parser.add_argument("--workers", type=int, default=4, help="Concurrent download threads")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = args.root.resolve()
    dest = args.destination if args.destination.is_absolute() else root / args.destination

    LOG.info("Acquiring Abdomen dataset to %s", dest)
    result = acquire_abdomen(dest, workers=args.workers)
    LOG.info("Acquisition completed: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
