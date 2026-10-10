"""Verify/package an explicitly approved final Lung model; never train."""
import argparse
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.lung_inference import prepare_package

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--model-version", required=True)
    a = p.parse_args()
    prepare_package(a.source, a.destination, model_version=a.model_version)
    print("Verified Lung package created; no model training performed.")
