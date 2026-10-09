"""Participant-safe nested CV for a frozen, uniformly pooled acoustic embedding."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from auriscore.oof_audit import best_at_sensitivity, threshold_tradeoff
import pandas as pd

C_GRID = (0.01, 0.1, 1.0, 10.0)
FEATURES = tuple(f"embedding_{i:02d}" for i in range(64))


def make_classifier(c: float, seed: int):
    """Preserve the diagnostic probe's fixed balanced L2 logistic policy."""
    return make_pipeline(StandardScaler(), LogisticRegression(
        C=c, penalty="l2", class_weight="balanced", solver="lbfgs",
        max_iter=1000, random_state=seed,
    ))


def inner_oof(data: pd.DataFrame, c: float, seed: int) -> np.ndarray:
    """Predict each outer-training participant once without fitting its scaler."""
    x = data.loc[:, FEATURES].to_numpy(dtype=float)
    y = data.label.eq("Present").to_numpy(dtype=int)
    if not np.isfinite(x).all() or len(set(data.participant_id)) != len(data):
        raise ValueError("Invalid or duplicate training embeddings")
    scores = np.full(len(data), np.nan)
    for fit, held in StratifiedKFold(5, shuffle=True, random_state=seed).split(x, y):
        if set(fit) & set(held):
            raise ValueError("Inner CV leakage")
        classifier = make_classifier(c, seed)
        classifier.fit(x[fit], y[fit])
        scores[held] = classifier.predict_proba(x[held])[:, 1]
    if not np.isfinite(scores).all():
        raise ValueError("Incomplete inner OOF predictions")
    return scores


def choose_c(data: pd.DataFrame, seed: int) -> tuple[float, pd.DataFrame]:
    """Select C from five-fold inner OOF, with sensitivity-first policy."""
    rows = []
    for c in C_GRID:
        scores = inner_oof(data, c, seed)
        predictions = data[["participant_id", "label"]].copy()
        predictions["probability"] = scores
        best = best_at_sensitivity(threshold_tradeoff(predictions), 0.90)
        rows.append({"C": c, **best})
    table = pd.DataFrame(rows)
    eligible = table.loc[table.sensitivity >= .90 - 1e-12]
    if len(eligible):
        chosen = eligible.sort_values(["f1", "specificity", "precision", "C"],
                                      ascending=[False, False, False, True], kind="stable").iloc[0]
    else:
        chosen = table.sort_values(["sensitivity", "f1", "C"],
                                   ascending=[False, False, True], kind="stable").iloc[0]
    return float(chosen.C), table

