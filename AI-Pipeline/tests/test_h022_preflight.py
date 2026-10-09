"""Focused, TRAIN-only H022 provenance and one-batch representation tests."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from h022_preflight import H021, audit_mining, digest, verify_lock  # noqa: E402


def test_h021_mining_is_exact_fold_local_and_hashed():
    report = audit_mining()
    assert report["fold_assignments_sha256"] == "75354a4188b1f23fd907f3f7a3e5a0cef1e0c83636cd205443c8e50572a5fa9e"
    assert [report["folds"][str(i)]["hard_negative_count"] for i in range(1, 6)] == [211, 215, 215, 212, 208]
    for fold in range(1, 6):
        item = report["folds"][str(fold)]
        assert item["hard_negative_count"] == math.ceil(item["eligible_absent_fit_recordings"] * .20)
        assert len(item["selected_recording_ids_sha256"]) == 64


def test_protocol_lock_and_no_global_oof_supervision():
    report = verify_lock()
    assert report["h021_protocol_sha256"] == digest(H021 / "protocol.json")
    for source in (ROOT / "scripts/train_h022_contrastive.py", ROOT / "scripts/h022_preflight.py"):
        code = source.read_text()
        assert "H021 / \"predictions_oof.csv\"" not in code
        assert "global_oof_fp" not in code
        assert "validation_participant_predictions" not in code


def test_reconciled_frequency_statistics_guard_does_not_reject_nonempty_fit(monkeypatch):
    import pandas as pd
    import auriscore.cnn as cnn
    monkeypatch.setattr(cnn, "_window", lambda *args, **kwargs: np.ones((40, 313, 1), dtype=np.float32))
    mean, std, frames = cnn._estimate_frequency_statistics(pd.DataFrame([{"recording_id": "synthetic"}]), ROOT, {})
    assert len(mean) == len(std) == 40 and frames == 313
    with pytest.raises(ValueError, match="empty training partition"):
        cnn._estimate_frequency_statistics(pd.DataFrame(), ROOT, {})


def test_h022_dataset_carries_mined_flags_and_unchanged_classification_examples(monkeypatch):
    import pandas as pd
    from auriscore import contrastive_acoustic as acoustic
    monkeypatch.setattr(acoustic, "spectrogram_shape", lambda config: (40, 313))
    frame = pd.DataFrame({"recording_id": ["hard", "ordinary", "declared_present"],
                          "label": ["Absent", "Absent", "Present"]})
    def examples(frame, root, config, include_weights, training, rng, multipliers):
        for item in frame.itertuples():
            yield np.zeros((40, 313, 1), np.float32), np.float32(item.label == "Present"), np.float32(multipliers[item.recording_id])
    monkeypatch.setattr(acoustic, "_example_iterator", examples)
    ds = acoustic.stage1_dataset(frame, ROOT, {"seed": 42, "cnn_batch_size": 3}, False,
        {"hard": 2.0, "ordinary": 1.0, "declared_present": 1.0}, {"hard"})
    (x, flags), labels, weights = next(iter(ds))
    assert x.shape == (3, 40, 313, 1)
    assert flags.numpy().tolist() == [True, False, False]
    assert labels.numpy().tolist() == [0.0, 0.0, 1.0]
    assert weights.numpy().tolist() == [2.0, 1.0, 1.0]
    with pytest.raises(ValueError, match="outside Stage-1"):
        acoustic.stage1_dataset(frame, ROOT, {"seed": 42}, False, hard_ids={"outer_eval_recording"})


def test_worker_import_is_static_and_does_not_start_training():
    import train_h022_contrastive as worker
    assert worker.NAME == "EXP-H022-fold-local-hard-negative-contrastive-representation"
    assert not (worker.H022 / "metrics.json").exists()


def test_one_tiny_synthetic_gradient_and_model_roundtrip(tmp_path):
    tf = pytest.importorskip("tensorflow")
    from auriscore.cnn import build_cnn_model
    from auriscore.contrastive_acoustic import ContrastiveAcousticTrainer, hard_negative_contrastive_loss

    tf.keras.utils.set_random_seed(42)
    base = build_cnn_model((40, 313, 1), {"cnn_architecture": "compact", "cnn_dropout": .30,
        "cnn_learning_rate": .001}, jit_compile=False)
    trainer = ContrastiveAcousticTrainer(base)
    trainer.compile(optimizer=tf.keras.optimizers.Adam(.001), jit_compile=False)
    x = tf.random.stateless_normal((4, 40, 313, 1), seed=(42, 1))
    labels = tf.constant([0., 0., 1., 1.])
    hard = tf.constant([True, False, False, False])
    weights = tf.constant([2., 1., 1., 1.])
    with tf.GradientTape() as tape:
        z, p = trainer.joint(x, training=True)
        representation = hard_negative_contrastive_loss(z, labels, hard)
        classification = tf.reduce_mean(tf.keras.losses.binary_crossentropy(labels[:, None], p) * weights)
        loss = classification + .10 * representation
    grads = tape.gradient(loss, base.trainable_variables)
    assert z.shape == (4, 64)
    assert float(representation) > 0
    assert np.isfinite([float(loss), float(representation), float(classification)]).all()
    assert all(g is not None and np.isfinite(g.numpy()).all() for g in grads)
    assert any(float(tf.linalg.global_norm([g])) > 0 for g in grads[:3])
    assert float(hard_negative_contrastive_loss(z, labels, tf.zeros_like(hard))) == 0
    trainer(x)
    trainer.train_step(((x, hard), labels, weights))
    tiny = tf.data.Dataset.from_tensor_slices(((x, hard), labels, weights)).batch(4)
    history = trainer.fit(tiny, validation_data=tiny, epochs=1, verbose=0)
    assert np.isfinite(history.history["val_loss"]).all()
    path = tmp_path / "tiny.keras"
    trainer.save(path)
    loaded = tf.keras.models.load_model(path)
    assert int(loaded.optimizer.iterations) == int(trainer.optimizer.iterations)
    assert loaded.acoustic_model.layers[-2].output.shape[-1] == 64
    assert np.isfinite(loaded.acoustic_model(x, training=False).numpy()).all()
    from auriscore.linear_head import make_classifier
    linear = make_classifier(1.0, 42)
    linear.fit(z.numpy(), np.array([0, 0, 1, 1]))
    assert np.isfinite(linear.predict_proba(z.numpy())).all()
