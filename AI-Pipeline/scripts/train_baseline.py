"""Train the fixed SVM and evaluate held-out subjects."""
import _bootstrap  # noqa: F401
from auriscore.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main("train_baseline"))
