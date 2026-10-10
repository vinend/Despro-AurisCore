"""Timestamped Lung process events and throttled callbacks; no fitting on import."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any


class TrainingLog:
    """Flush readable stderr events and optionally persist matching JSONL records."""

    def __init__(self, interval_s: float = 30):
        if not 0 < interval_s < float("inf"):
            raise ValueError("Progress interval must be finite and positive")
        self.interval_s = interval_s
        self.started = time.monotonic()
        self.path = None
        self.last_progress = {}

    def bind(self, output: Path) -> None:
        """Attach an event file inside an already-created immutable experiment."""
        self.path = Path(output) / "process.jsonl"

    def event(self, stage: str, **details: Any) -> None:
        """Write one process event without hiding exceptions or TensorFlow output."""
        record = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "elapsed_s": round(time.monotonic() - self.started, 3), "stage": stage, **details}
        print(f"[{record['timestamp']} +{record['elapsed_s']:.1f}s] {stage} "
              + " ".join(f"{key}={value}" for key, value in details.items()), file=sys.stderr, flush=True)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, allow_nan=False) + "\n")

    def progress(self, stage: str, completed: int, total: int) -> None:
        """Emit first/last items and time-throttled progress, avoiding per-window spam."""
        now = time.monotonic()
        if completed in (1, total) or now - self.last_progress.get(stage, now) >= self.interval_s:
            self.event(stage, completed=completed, total=total, percent=round(100 * completed / total, 1))
            self.last_progress[stage] = now


def runtime_details(tf: Any) -> dict:
    """Report visible logical GPUs; visibility does not prove every op runs on GPU."""
    physical = tf.config.list_physical_devices("GPU")
    logical = tf.config.list_logical_devices("GPU")
    return {"tensorflow": tf.__version__, "logical_gpus": [device.name for device in logical],
            "gpu_names": [tf.config.experimental.get_device_details(device).get("device_name", device.name)
                          for device in physical], "execution": "GPU available" if logical else "CPU fallback"}


def process_callback(log: TrainingLog, *, epochs: int, steps: int, early_stopper: Any = None,
                     checkpoint: Path | None = None) -> Any:
    """Log epoch/batch timing and the actual Keras early-stop checkpoint decision."""
    import tensorflow as tf

    class ProcessCallback(tf.keras.callbacks.Callback):
        def on_epoch_begin(self, epoch, logs=None):
            self.epoch = epoch + 1
            self.started = time.monotonic()
            log.event("epoch_started", epoch=self.epoch, maximum_epochs=epochs, batches=steps,
                      learning_rate=float(tf.keras.backend.get_value(self.model.optimizer.learning_rate)))

        def on_train_batch_end(self, batch, logs=None):
            log.progress(f"epoch_{self.epoch}_training_batches", batch + 1, steps)

        def on_test_begin(self, logs=None):
            log.event("validation_started", epoch=self.epoch)

        def on_epoch_end(self, epoch, logs=None):
            metrics = {key: float(value) if value is not None and float("-inf") < float(value) < float("inf") else None
                       for key, value in (logs or {}).items()}
            details = {"epoch": epoch + 1, "duration_s": round(time.monotonic() - self.started, 3), **metrics}
            if early_stopper is not None:
                best = getattr(early_stopper, "best", None)
                details.update(best_epoch=int(getattr(early_stopper, "best_epoch", 0)) + 1,
                               best_val_loss=float(best) if best is not None and abs(float(best)) < float("inf") else None,
                               epochs_without_improvement=int(early_stopper.wait),
                               patience=int(early_stopper.patience), early_stop=bool(self.model.stop_training))
            log.event("epoch_completed", **details)
            if (early_stopper is not None and checkpoint is not None
                    and getattr(early_stopper, "best_epoch", -1) == epoch and Path(checkpoint).is_file()):
                log.event("best_checkpoint_saved", epoch=epoch + 1, path=str(checkpoint))

        def on_train_end(self, logs=None):
            details = {"early_stopped": bool(self.model.stop_training)}
            if early_stopper is not None:
                details.update(restored_best_weights=bool(early_stopper.restore_best_weights),
                               best_epoch=int(getattr(early_stopper, "best_epoch", 0)) + 1)
            log.event("fitting_finished", **details)

    return ProcessCallback()
