"""Build deterministic float spectrogram tensors and their metadata manifest."""
import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.cnn import prepare_spectrogram_config
from auriscore.config import load_config
from auriscore.io import read_table
from auriscore.pipeline import stamp
from auriscore.spectrogram_cache import build_cache_manifest, render_previews


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--config", type=Path, default=Path("configs/heart_spectrogram_cnn.yaml")
    )
    parser.add_argument(
        "--previews", type=int, default=12,
        help="Number of human-QC PNGs to render; PNG files are never training inputs",
    )
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        config = load_config(root / args.config)
        stamp(root, config, "segments", verify=True)
        segments = read_table(root / "data/processed/segments.csv")
        training = segments[segments.split.eq("train")]
        prepared = prepare_spectrogram_config(training, root, config)
        manifest = build_cache_manifest(segments, root, prepared)
        previews = render_previews(manifest, root, args.previews)
        print(f"Cached {len(manifest)} spectrogram tensors; rendered {len(previews)} QC previews")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"Cannot cache spectrograms: {exc}\n")

