"""Run one named Heart CNN variant with the same resumable queue machinery."""
from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.config import load_config
from auriscore.experiment_queue import queue_lock, run_one


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=Path("configs/heart_cnn.yaml"))
    parser.add_argument("--name", required=True)
    change = parser.add_mutually_exclusive_group(required=True)
    change.add_argument("--conservative-augmentation", action="store_true")
    change.add_argument("--dropout", type=float)
    change.add_argument("--learning-rate", type=float)
    change.add_argument("--residual-se", action="store_true")
    change.add_argument("--per-frequency-normalization", action="store_true")
    change.add_argument("--n-mels", type=int)
    args = parser.parse_args()
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    try:
        base = load_config(config_path)
        overrides = {}
        if args.conservative_augmentation:
            overrides = dict(augmentation_enabled=True, augmentation_gain_db=2.0,
                             augmentation_time_shift_fraction=.03,
                             augmentation_noise_probability=.25,
                             augmentation_snr_db_min=25.0,
                             augmentation_snr_db_max=35.0,
                             augmentation_frequency_mask_bins=2,
                             augmentation_frequency_mask_count=1,
                             augmentation_time_mask_frames=8,
                             augmentation_time_mask_count=1)
        elif args.dropout is not None:
            if not 0 <= args.dropout < 1:
                raise ValueError("dropout must be in [0, 1)")
            overrides["cnn_dropout"] = args.dropout
        elif args.residual_se:
            overrides["cnn_architecture"] = "residual_se"
        elif args.per_frequency_normalization:
            overrides = {"spectrogram_normalization": "per_frequency",
                         "spectrogram_normalization_clip": 5.0}
        elif args.n_mels is not None:
            if args.n_mels < 8 or args.n_mels > int(base["n_fft"]) // 2 + 1:
                raise ValueError("n_mels must be between 8 and the FFT bin count")
            overrides["n_mels"] = args.n_mels
        else:
            if args.learning_rate is None or args.learning_rate <= 0:
                raise ValueError("learning rate must be positive")
            overrides["cnn_learning_rate"] = args.learning_rate
        with queue_lock(root):
            print(run_one(root, base, {"name": args.name, "overrides": overrides}), flush=True)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"Cannot train experiment: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
