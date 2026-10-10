"""Explicitly open sealed HF official test once after freezing the final candidate."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.lung_holdout import evaluate

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--model-version", required=True)
    p.add_argument("--root", type=Path, default=Path("data/external/hf-lung-v1/extracted"))
    p.add_argument("--manifest", type=Path, default=Path("data/processed/lung"))
    p.add_argument("--open-sealed-test", action="store_true")
    a = p.parse_args()
    if not a.open_sealed_test:
        p.error("Official test stays sealed without explicit --open-sealed-test authorization")
    evaluate(a.candidate, a.root, a.manifest, model_version=a.model_version, authorized=True)
