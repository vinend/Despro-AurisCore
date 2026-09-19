"""Train the optional log-mel CNN and select its screening threshold on validation data."""
import _bootstrap  # noqa: F401
from auriscore.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main("train_cnn", default_config="configs/heart_cnn.yaml"))
