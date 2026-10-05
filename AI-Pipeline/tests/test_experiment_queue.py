"""Filesystem recovery checks; these tests never train a neural network."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from auriscore.experiment_queue import (
    find_experiment, is_completed, load_plan, queue_lock, run_one, status_rows,
)
from auriscore.experiment_runtime import (
    atomic_json, reconcile_history, sync_best_model,
)


def test_committed_history_ignores_partial_epoch(tmp_path: Path) -> None:
    experiment = tmp_path / "EXP-H001-cnn-compact"
    checkpoint = experiment / "checkpoints"
    backup = checkpoint / "backup"
    backup.mkdir(parents=True)
    atomic_json(backup / "training_metadata.json", {"epoch": 2, "batch": 0})
    pd.DataFrame({"epoch": [0, 1, 2], "loss": [.8, .6, .4],
                  "val_loss": [.7, .5, .3], "accuracy": [.5, .6, .7],
                  "val_accuracy": [.5, .6, .7]}).to_csv(checkpoint / "keras_history.csv", index=False)
    (checkpoint / "best-epoch-0002-0.500000.keras").write_bytes(b"best model")
    committed = reconcile_history(experiment)
    assert list(committed.epoch) == [0, 1]
    assert list(pd.read_csv(experiment / "history.csv").epoch) == [1, 2]
    assert list(pd.read_csv(checkpoint / "keras_history.csv").epoch) == [0, 1]
    assert sync_best_model(experiment, committed) == (2, .5, 0)
    assert (experiment / "best_model.keras").read_bytes() == b"best model"


def test_completed_run_skips_without_training_or_duplicate(tmp_path: Path) -> None:
    directory = tmp_path / "results" / "EXP-H004-cnn-dropout-050"
    directory.mkdir(parents=True)
    (directory / "heart_cnn.keras").write_bytes(b"existing model")
    (directory / "metrics.json").write_text(json.dumps({"training_epochs": 3,
        "training_history": {"val_loss": [.8, .5, .6]}}), encoding="utf-8")
    assert run_one(tmp_path, {}, {"name": "cnn-dropout-050", "overrides": {}}).startswith("skipped")
    assert find_experiment(tmp_path, "cnn-dropout-050") == directory
    assert (directory / "best_model.keras").read_bytes() == b"existing model"
    assert json.loads((directory / "status.json").read_text())["status"] == "completed"
    assert len(list((tmp_path / "results").iterdir())) == 1
    atomic_json(directory / "config.json", {"seed": 1})
    with pytest.raises(ValueError, match="Configuration differs"):
        run_one(tmp_path, {"seed": 42}, {"name": "cnn-dropout-050", "overrides": {}})


def test_managed_run_requires_completed_status(tmp_path: Path) -> None:
    directory = tmp_path / "EXP-H008-cnn-new"
    directory.mkdir()
    (directory / "request.json").write_text("{}", encoding="utf-8")
    (directory / "metrics.json").write_text("{}", encoding="utf-8")
    (directory / "best_model.keras").write_bytes(b"model")
    atomic_json(directory / "status.json", {"status": "running"})
    assert not is_completed(directory)
    atomic_json(directory / "status.json", {"status": "completed"})
    assert is_completed(directory)


def test_queue_plan_and_lock(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"schema_version": 1, "experiments": [
        {"name": "cnn-new", "overrides": {}}
    ]}), encoding="utf-8")
    plan = load_plan(plan_path)
    assert status_rows(tmp_path, plan)[0]["status"] == "queued"
    with queue_lock(tmp_path):
        with pytest.raises(RuntimeError, match="already running"):
            with queue_lock(tmp_path):
                pass


def test_incomplete_managed_run_reuses_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auriscore import cnn, experiment_queue, visualization

    item = {"name": "cnn-new", "overrides": {}}
    base = {"model_type": "cnn", "seed": 42}
    directory = tmp_path / "results" / "EXP-H009-cnn-new"
    directory.mkdir(parents=True)
    requested = dict(base, experiment_name="cnn-new")
    atomic_json(directory / "request.json", experiment_queue._request(requested))
    atomic_json(directory / "config.json", requested)
    atomic_json(directory / "status.json", {"status": "failed", "current_epoch": 2,
                "segments_sha256": "same data"})
    monkeypatch.setattr(experiment_queue, "wait_for_other_trainers", lambda: None)
    monkeypatch.setattr(experiment_queue, "verify_segments", lambda *_: "same data")
    monkeypatch.setattr(experiment_queue, "read_table", lambda *_: pd.DataFrame())
    monkeypatch.setattr(visualization, "update_comparison", lambda *_: None)

    def fake_train(_segments, _config, _root, output_dir, experiment_dir):
        assert experiment_dir == directory
        assert output_dir == directory / "intermediate"
        (directory / "best_model.keras").write_bytes(b"resumed model")
        atomic_json(directory / "metrics.json", {"training_epochs": 3,
                    "training_history": {"val_loss": [.8, .5, .6]}})
        return {"tensorflow": "2.21.0"}

    monkeypatch.setattr(cnn, "train_cnn", fake_train)
    assert run_one(tmp_path, base, item) == f"completed {directory.name}"
    assert json.loads((directory / "status.json").read_text())["current_epoch"] == 3
    assert len(list((tmp_path / "results").iterdir())) == 1
