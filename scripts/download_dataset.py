"""Download the original public CirCor release with checksums."""
import _bootstrap  # noqa: F401
from auriscore.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main("download_dataset"))
