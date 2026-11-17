"""Verify TRAIN-only spectral tilt preserves the Lung training targets."""
import numpy as np
import pandas as pd
import pytest

from auriscore.lung_training import build_dataset


def test_tilt_changes_only_training_features(tmp_path):
    pytest.importorskip("tensorflow")
    x = np.zeros((5, 8), np.float32)
    y = np.zeros((5, 3), np.float32)
    y[2, 1] = 1
    np.savez(tmp_path / "a.npz", features=x, targets=y, mask=np.ones_like(y))
    rows = pd.DataFrame({"file": ["a.npz"], "split": ["train"]})

    def dataset(training, tilt):
        return build_dataset(tmp_path, rows, np.zeros(8), np.ones(8), batch_size=1,
                             training=training, seed=42, spectral_tilt_db=tilt)

    base, labels = next(iter(dataset(True, 0)))
    tilted, same_labels = next(iter(dataset(True, 8)))
    same_tilted, _ = next(iter(dataset(True, 8)))
    assert not np.array_equal(tilted, base)
    np.testing.assert_array_equal(same_labels, labels)
    np.testing.assert_array_equal(same_tilted, tilted)
    np.testing.assert_allclose(tilted[0, 0], -tilted[0, 0, ::-1], atol=1e-6)
    with pytest.raises(ValueError, match="TRAIN-only"):
        dataset(False, 8)
