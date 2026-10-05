"""Persistent, epoch-level state for resumable Heart CNN experiments.

The Keras backup is the source of truth for committed epochs. CSV rows or best
checkpoints written before a backup are ignored after an interrupted epoch.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import pandas as pd


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    """Replace a small JSON state file without exposing a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def committed_epochs(directory: Path) -> int:
    """Return the last complete epoch recorded by Keras BackupAndRestore."""
    backup = directory / "checkpoints" / "backup"
    primary = backup / "training_metadata.json"
    previous = backup / "training_metadata.json.bkp"
    for candidate in (primary, previous):
        if candidate.exists():
            try:
                return max(0, int(json.loads(candidate.read_text(encoding="utf-8"))["epoch"]))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return 0


def _raw_history_path(directory: Path) -> Path:
    return directory / "checkpoints" / "keras_history.csv"


def reconcile_history(directory: Path) -> pd.DataFrame:
    """Discard CSV rows beyond the last recoverable Keras epoch."""
    raw = _raw_history_path(directory)
    committed = committed_epochs(directory)
    if not raw.exists():
        if committed:
            raise RuntimeError("Backup has completed epochs but its history CSV is missing")
        _write_public_history(directory, pd.DataFrame(columns=[
            "epoch", "loss", "val_loss", "accuracy", "val_accuracy",
        ]))
        return pd.DataFrame()
    try:
        original = pd.read_csv(raw)
    except pd.errors.EmptyDataError as exc:
        raise RuntimeError(f"Training history CSV is empty: {raw}") from exc
    if "epoch" not in original:
        raise ValueError(f"Training history has no epoch column: {raw}")
    table = original[original.epoch.lt(committed)].drop_duplicates("epoch", keep="first")
    table = table.sort_values("epoch").reset_index(drop=True)
    if len(table) != committed or list(table.epoch.astype(int)) != list(range(committed)):
        raise RuntimeError("Training history and Keras backup disagree on completed epochs")
    if not table.equals(original):
        table.to_csv(raw, index=False)
    _write_public_history(directory, table)
    if committed == 0:
        # A weights file without metadata is an uncommitted partial backup.
        backup = directory / "checkpoints" / "backup"
        for path in backup.glob("*.weights.h5"):
            path.rename(path.with_name(f"{path.name}.uncommitted.{int(time.time())}"))
    return table


def _write_public_history(directory: Path, table: pd.DataFrame) -> None:
    public = table.copy()
    if not public.empty:
        public["epoch"] = public["epoch"].astype(int) + 1
    destination = directory / "history.csv"
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    public.to_csv(temporary, index=False)
    os.replace(temporary, destination)


def history_dict(table: pd.DataFrame) -> dict[str, list[float]]:
    """Return complete Keras series for metrics and plotting."""
    return {
        column: [float(value) for value in table[column]]
        for column in table.columns if column != "epoch"
    }


def best_record(table: pd.DataFrame) -> tuple[int | None, float | None, int]:
    """Return one-based best epoch, loss, and epochs since improvement."""
    if table.empty:
        return None, None, 0
    if "val_loss" not in table:
        raise ValueError("Training history has no val_loss column")
    values = table.val_loss.astype(float)
    best_index = int(values.idxmin())
    return int(table.loc[best_index, "epoch"]) + 1, float(values.iloc[best_index]), len(table) - best_index - 1


def _best_checkpoint(directory: Path, best_epoch: int, best_loss: float) -> Path:
    matches = list((directory / "checkpoints").glob(f"best-epoch-{best_epoch:04d}-*.keras"))
    if not matches:
        raise FileNotFoundError(f"No model checkpoint for best epoch {best_epoch}")
    def distance(path: Path) -> float:
        return abs(float(path.stem.rsplit("-", 1)[-1]) - best_loss)
    selected = min(matches, key=distance)
    if distance(selected) > 0.00001:
        raise RuntimeError("Best checkpoint loss does not match committed history")
    return selected


def sync_best_model(directory: Path, table: pd.DataFrame) -> tuple[int | None, float | None, int]:
    """Expose the best committed checkpoint as best_model.keras."""
    best_epoch, best_loss, wait = best_record(table)
    if best_epoch is None or best_loss is None:
        return None, None, wait
    source = _best_checkpoint(directory, best_epoch, best_loss)
    destination = directory / "best_model.keras"
    temporary = directory / f".best_model.{os.getpid()}.keras"
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    return best_epoch, best_loss, wait


def training_callbacks(tf: Any, directory: Path, patience: int,
                       previous: pd.DataFrame) -> list[Any]:
    """Build Keras callbacks in commit order: log, best, backup, status."""
    checkpoints = directory / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    prior_epoch, prior_loss, _ = sync_best_model(directory, previous)
    raw_history = _raw_history_path(directory)

    class Progress(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch: int, logs: dict[str, Any] | None = None) -> None:
            table = reconcile_history(directory)
            if len(table) != epoch + 1:
                raise RuntimeError("Epoch was not committed before status update")
            best_epoch, best_loss, wait = sync_best_model(directory, table)
            status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
            status.update(status="running", current_epoch=len(table), best_epoch=best_epoch,
                          best_val_loss=best_loss, updated_at=time.time(), pid=os.getpid())
            atomic_json(directory / "status.json", status)
            if wait >= patience and epoch > 0:
                self.model.stop_training = True

    return [
        tf.keras.callbacks.CSVLogger(str(raw_history), append=not previous.empty),
        tf.keras.callbacks.ModelCheckpoint(
            str(checkpoints / "best-epoch-{epoch:04d}-{val_loss:.6f}.keras"),
            monitor="val_loss", mode="min", save_best_only=True,
            initial_value_threshold=prior_loss,
        ),
        tf.keras.callbacks.BackupAndRestore(
            str(checkpoints / "backup"), save_freq="epoch",
            double_checkpoint=True, delete_checkpoint=False,
        ),
        Progress(),
    ]
