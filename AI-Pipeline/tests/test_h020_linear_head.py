"""Focused H020 fold, scaler, threshold, and artifact-boundary checks."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from auriscore.linear_head import C_GRID, FEATURES, choose_c, inner_oof, make_classifier
from auriscore.oof_audit import best_at_sensitivity, threshold_tradeoff
from auriscore.oof_audit import verify_train_oof


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts/run_h020_linear.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("run_h020_linear", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cached_fold_membership_and_encoder_integrity():
    module = _script()
    assignments, inventory, protocol = module.inputs()
    assert len(inventory) == 568
    assert protocol["stage1_sources"]
    for fold in range(1, 6):
        fit, held = module.fold_cache(fold)
        assert set(fit.participant_id).isdisjoint(held.participant_id)
        assert set(held.participant_id) == set(assignments.loc[(assignments.fold == fold) & (assignments.role == "outer_eval"), "participant_id"])


def test_inner_cv_finite_deterministic_and_train_only():
    rng = np.random.default_rng(42)
    frame = pd.DataFrame(rng.normal(size=(60, 64)), columns=FEATURES)
    frame["participant_id"] = [str(i) for i in range(60)]
    frame["label"] = ["Present" if i % 5 == 0 else "Absent" for i in range(60)]
    result = inner_oof(frame, 1.0, 43)
    assert len(result) == len(frame)
    assert np.isfinite(result).all() and np.all((result >= 0) & (result <= 1))
    assert np.array_equal(result, inner_oof(frame, 1.0, 43))
    selected, table = choose_c(frame, 43)
    assert selected in C_GRID and set(table.C) == set(C_GRID)


def test_scaler_is_fitted_only_on_fit_values():
    x_fit = np.vstack([np.zeros((8, 64)), np.ones((8, 64))])
    y = np.array([0, 1] * 8)
    held = np.full((2, 64), 1000.0)
    model = make_classifier(1.0, 42)
    model.fit(x_fit, y)
    model.predict_proba(held)
    assert np.allclose(model.named_steps["standardscaler"].mean_, .5)


def test_threshold_sensitivity_constraint():
    p = pd.DataFrame({"label": ["Present", "Present", "Absent", "Absent"],
                      "probability": [.8, .4, .3, .2]})
    best = best_at_sensitivity(threshold_tradeoff(p), .90)
    assert best["sensitivity"] >= .90 and best["fn"] == 0


def test_invalid_cache_rejected_without_evaluation(monkeypatch):
    module = _script()
    original = module.fold_cache

    def leak(fold):
        fit, held = original(fold)
        fit = pd.concat([fit, held.iloc[:1]], ignore_index=True)
        return fit, held

    monkeypatch.setattr(module, "fold_cache", leak)
    with pytest.raises(ValueError):
        module.inputs()


def test_no_validation_or_holdout_access_in_h020():
    module = _script()
    source = (Path(__file__).resolve().parents[1] / "scripts/run_h020_linear.py").read_text()
    assert "validation_participant_predictions.csv" not in source
    assert "test_predictions.csv" not in source
    assert "evaluate_holdout" not in source
    assert module.OUT.name == "EXP-H020-linear-participant-head"


def test_completed_artifact_schema_and_oof_integrity():
    module = _script()
    assignments, inventory, _ = module.inputs()
    required = ["protocol.json", "protocol_sha256.txt", "config.json",
                "fold_hyperparameters.csv", "fold_metrics.csv", "predictions_oof.csv",
                "threshold_tradeoff.csv", "metrics.json", "comparison_h016_h020.csv",
                "roc_curve.png", "pr_curve.png", "score_distribution.png",
                "summary.json", "summary.md"]
    assert all((module.OUT / name).is_file() for name in required)
    pred = pd.read_csv(module.OUT / "predictions_oof.csv", dtype={"participant_id": str})
    verify_train_oof(pred, assignments, inventory)
    assert len(list((module.OUT / "models").glob("fold_*_scaler_logistic.npz"))) == 5

