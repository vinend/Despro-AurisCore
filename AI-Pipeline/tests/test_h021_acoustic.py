"""Focused H021 train-only mining, weighting, and split protections."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from auriscore.hard_negative_mining import inner_assignments, inner_fit_early, select_hard_negatives


def _worker():
    path = Path(__file__).resolve().parents[1] / "scripts/train_h021_acoustic.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("train_h021_acoustic", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_outer_fold_reuse_and_inner_no_leakage():
    worker = _worker()
    frame, assignments, audit, inventory = worker.preflight()
    assert len(inventory) == 568
    assert list(assignments.loc[assignments.role == "outer_eval"].groupby("fold").size()) == [114, 114, 114, 113, 113]
    for fold in range(1, 6):
        parts = worker.partitions(frame, assignments, audit, fold)
        outer_train = pd.concat([parts["fit"], parts["early_stop"]], ignore_index=True)
        held_outer = set(parts["outer_eval"].subject_group.astype(str))
        inner = inner_assignments(outer_train, held_outer, fold)
        assert len(inner) == 568 - len(held_outer)
        assert inner.participant_id.is_unique
        assert set(inner.participant_id).isdisjoint(held_outer)
        for inner_fold in range(1, 6):
            held = set(inner.loc[inner.inner_fold == inner_fold, "participant_id"])
            fit, early = inner_fit_early(outer_train, held, fold, inner_fold)
            assert not ((fit | early) & (held | held_outer))
            assert not (fit & early)
            assert fit | early | held == set(inner.participant_id)


def test_exact_deterministic_top_20_percent_and_weights():
    scores = pd.DataFrame({
        "participant_id": [str(i) for i in range(12)],
        "recording_id": [f"r{i}" for i in range(12)],
        "site": ["AV"] * 12, "inner_fold": [i % 5 + 1 for i in range(12)],
        "true_label": ["Absent"] * 10 + ["Present"] * 2,
        "cross_fitted_score": [.8, .9, .2, .1, .7, .6, .5, .4, .3, .0, .99, .98],
    })
    fit_neg = {f"r{i}" for i in range(10)}
    selected = select_hard_negatives(scores, fit_neg)
    assert selected.loc[selected.hard_negative, "recording_id"].tolist() == ["r0", "r1"]
    assert int(selected.hard_negative.sum()) == math.ceil(.2 * len(fit_neg))
    assert set(selected.sample_weight) == {1.0, 2.0}
    assert selected.loc[selected.true_label == "Present", "hard_negative"].sum() == 0
    assert selected.equals(select_hard_negatives(scores, fit_neg))


def test_outer_eval_recording_cannot_enter_selection():
    scores = pd.DataFrame({"participant_id": ["1", "2"], "recording_id": ["a", "b"],
                           "site": ["AV", "MV"], "inner_fold": [1, 2],
                           "true_label": ["Absent", "Absent"], "cross_fitted_score": [.2, .9]})
    with pytest.raises(ValueError):
        select_hard_negatives(scores, {"a", "outside_outer_fold"})


def test_multiplier_enters_stage1_sample_weights(monkeypatch):
    from auriscore import cnn
    frame = pd.DataFrame({"subject_group": ["n1", "n2", "p1", "p2"],
                          "label": ["Absent", "Absent", "Present", "Present"],
                          "recording_id": ["a", "b", "c", "d"]})
    monkeypatch.setattr(cnn, "_window", lambda *args, **kwargs: np.zeros((40, 313, 1), dtype=np.float32))
    samples = list(cnn._example_iterator(frame, Path("."), {"seed": 42}, True,
                                         recording_multiplier={"a": 2.0, "b": 1.0, "c": 1.0, "d": 1.0}))
    assert [float(x[2]) for x in samples] == [2.0, 1.0, 1.0, 1.0]
    with pytest.raises(ValueError):
        list(cnn._example_iterator(frame, Path("."), {"seed": 42}, True,
                                   recording_multiplier={"a": 2.0}))


def test_no_external_validation_or_sealed_test_calls():
    path = Path(__file__).resolve().parents[1] / "scripts/train_h021_acoustic.py"
    source = path.read_text()
    assert 'read_one_split(' not in source
    assert 'evaluate_holdout' not in source
    assert 'validation_predictions.csv' not in source
    assert 'test_predictions.csv' not in source


def test_existing_h020_nested_classifier_policy():
    from auriscore.linear_head import C_GRID, make_classifier
    assert C_GRID == (.01, .1, 1.0, 10.0)
    classifier = make_classifier(1.0, 42)
    assert classifier.named_steps["logisticregression"].class_weight == "balanced"


def test_locked_protocol_and_prelaunch_artifact_schema():
    worker = _worker()
    frame, _, _, _ = worker.preflight()
    worker.verify_lock(frame)
    protocol_path = worker.A / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    assert hashlib.sha256(protocol_path.read_bytes()).hexdigest() == (worker.A / "protocol_sha256.txt").read_text().strip()
    assert protocol["hard_negative_fraction"] == .20
    assert protocol["hard_negative_weight_multiplier"] == 2.0
    assert protocol["outer_fold_assignments_sha256"]
    assert (worker.A / "config.json").is_file()
    assert json.loads((worker.R / "status.json").read_text())["status"] == "queued"

