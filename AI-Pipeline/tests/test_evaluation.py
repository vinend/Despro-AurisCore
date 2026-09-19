import numpy as np
import pandas as pd
import pytest

from auriscore.evaluation import evaluate, select_screening_threshold
from auriscore.holdout import lock_holdout


def validation_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "subject_id": ["a", "b", "c", "d", "e", "f"],
        "subject_group": ["a", "b", "c", "d", "e", "f"],
        "recording_id": ["ar", "br", "cr", "dr", "er", "fr"],
        "label": ["Absent", "Absent", "Absent", "Present", "Present", "Present"],
        "split": ["validation"] * 6,
    })


def test_threshold_selection_prioritizes_sensitivity():
    frame = validation_frame()
    scores = np.array([-2.0, -1.0, 0.4, 0.1, 0.5, 0.9])
    selected = select_screening_threshold(frame, scores, target_sensitivity=1.0, min_specificity=0.5)
    assert selected["threshold"] == pytest.approx(0.1)
    assert selected["validation_subject_metrics"]["recall_sensitivity"] == 1.0
    assert selected["validation_subject_metrics"]["specificity"] == pytest.approx(2 / 3)
    result, predictions = evaluate(frame, scores, selected["threshold"])
    assert result["subject"]["confusion_matrix"] == [[2, 1], [0, 3]]
    assert set(predictions.screening_result) == {"murmur present screening", "murmur absent screening"}


def test_exposed_holdout_cannot_be_relabelled_fresh(tmp_path, config):
    frame = pd.DataFrame({
        "subject_id": ["a", "b"],
        "subject_group": ["a", "b"],
        "recording_id": ["ar", "br"],
        "sha256": ["a" * 64, "b" * 64],
        "split": ["train", "test"],
    })
    with pytest.raises(ValueError, match="historical split"):
        lock_holdout(frame, config, tmp_path)


def test_cnn_model_shape(config):
    tf = pytest.importorskip("tensorflow")
    from auriscore.cnn import build_cnn_model

    cnn_config = dict(config, cnn_dropout=0.2, cnn_learning_rate=1e-3)
    model = build_cnn_model((40, 128, 1), cnn_config)
    output = model(tf.zeros((2, 40, 128, 1)), training=False)
    assert tuple(output.shape) == (2, 1)
