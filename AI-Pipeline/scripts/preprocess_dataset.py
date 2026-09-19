"""Preprocess recordings and index windows."""
import _bootstrap  # noqa: F401
from auriscore.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main("preprocess_dataset"))
