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

def test_active_training_processes_ignores_own_hierarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    from auriscore import experiment_queue

    class FakeProcess:
        def __init__(self, pid, cmdline, parents=(), children=()):
            self.pid = pid
            self.info = {"cmdline": cmdline}
            self._parents = [FakeProcess(p, []) for p in parents]
            self._children = [FakeProcess(c, []) for c in children]

        def parents(self):
            return self._parents

        def children(self, recursive=True):
            return self._children

    # Current process is 200, parent launcher stub is 100, child is 300, external is 999
    fake_current = FakeProcess(200, ["python.exe", "scripts/run_experiment_queue.py"], parents=[100], children=[300])
    all_processes = [
        FakeProcess(100, [r".venv\Scripts\python.exe", "scripts/run_experiment_queue.py"]),  # launcher stub
        fake_current,  # self
        FakeProcess(300, ["python.exe", "scripts/train_cnn.py"]),  # worker child
        FakeProcess(999, ["python.exe", "scripts/train_cnn.py", "--name", "other-run"]),  # external trainer
    ]

    class FakePsutil:
        def Process(self, pid=None):
            return fake_current

        def process_iter(self, attrs=None):
            return all_processes

    monkeypatch.setattr(experiment_queue, "psutil", FakePsutil())
    monkeypatch.setattr(experiment_queue.os, "getpid", lambda: 200)

    found = experiment_queue.active_training_processes()
    # Should only find the external trainer (999), not 100 (launcher stub), 200 (self), or 300 (child)
    assert len(found) == 1
    assert found[0]["pid"] == 999
    assert found[0]["name"] == "other-run"

def test_wait_for_other_trainers_and_skip_wait(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    from auriscore import experiment_queue

    real_wait = experiment_queue.wait_for_other_trainers
    called = False
    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True

    # 1. Verify skip_wait bypasses wait_for_other_trainers in run_one
    monkeypatch.setattr(experiment_queue, "wait_for_other_trainers", fail_if_called)
    item = {"name": "cnn-test", "overrides": {}}
    base = {"model_type": "cnn", "seed": 42}
    directory = Path("nonexistent")
    monkeypatch.setattr(experiment_queue, "find_experiment", lambda *_: directory)
    monkeypatch.setattr(experiment_queue, "is_completed", lambda *_: True)
    monkeypatch.setattr(experiment_queue, "_check_existing_config", lambda *_: None)
    monkeypatch.setattr(experiment_queue, "backfill_completed", lambda *_: None)
    experiment_queue.run_one(Path("."), base, item, skip_wait=True)
    assert not called

    # 2. Test wait_for_other_trainers prints using real_wait
    poll_count = 0
    def fake_active():
        nonlocal poll_count
        poll_count += 1
        if poll_count >= 2:
            return []
        return [{"pid": 8888, "script": "train_cnn.py"}]

    monkeypatch.setattr(experiment_queue, "active_training_processes", fake_active)
    real_wait(interval_seconds=0, timeout_seconds=10)
    captured = capsys.readouterr().out
    assert "Waiting for existing active process: PID 8888" in captured
    assert "Prior active process finished. Resuming training queue..." in captured
