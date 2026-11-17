"""Exercise L030 frame differences, training and model serialization."""
import numpy as np
import pytest

from auriscore.lung_models import build_model


def test_delta_preserves_frames_and_round_trips(tmp_path):
    tf = pytest.importorskip("tensorflow")
    model = build_model((16, 16), ["wheeze", "rhonchi", "crackle"],
                        temporal_dilation=16, temporal_delta=True,
                        loss_numerics="stable_bce")
    signal = np.broadcast_to(np.arange(16, dtype=np.float32)[None, :, None], (1, 16, 16))
    inspect = tf.keras.Model(model.input, model.get_layer("logmel_with_delta").output)
    channels = inspect(signal).numpy()[0]
    np.testing.assert_array_equal(channels[..., 0], signal[0])
    np.testing.assert_array_equal(channels[0, :, 1], 0)
    np.testing.assert_array_equal(channels[1:, :, 1], 1)
    targets = np.ones((1, 16, 6), np.float32)
    assert np.isfinite(model.train_on_batch(signal, targets))
    path = tmp_path / "delta.keras"
    model.save(path)
    restored = tf.keras.models.load_model(path, compile=False)
    np.testing.assert_allclose(model(signal, training=False), restored(signal, training=False))
