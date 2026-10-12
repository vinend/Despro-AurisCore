"""Convolutional Recurrent Neural Network (CRNN) for Sound Event Detection."""
from __future__ import annotations

from typing import Any

from .cnn import require_tensorflow


def build_crnn_sed_model(input_shape: tuple[int, int, int], config: dict[str, Any]) -> Any:
    """Build a CRNN with frequency-only pooling, bidirectional recurrent context, and time-distributed output."""
    tf = require_tensorflow()

    # Input: (frequency_bins, time_frames, 1), e.g. (40, 313, 1)
    inputs = tf.keras.Input(shape=input_shape, name="spectrogram")
    x = inputs

    # 1. Convolutional feature extractor (pooling along frequency ONLY, keeping time resolution)
    filters_list = (32, 64, 64)
    for filters in filters_list:
        x = tf.keras.layers.Conv2D(filters, 3, padding="same", use_bias=False)(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.Activation("relu")(x)
        x = tf.keras.layers.MaxPooling2D(pool_size=(2, 1))(x)  # Pool freq / 2, keep time

    # x shape is now: (batch, freq // 8, time_frames, 64) e.g. (batch, 5, 313, 64)
    # Permute to (batch, time_frames, freq // 8, 64)
    x = tf.keras.layers.Permute((2, 1, 3))(x)

    # Flatten frequency and channels into feature dimension: (batch, time_frames, (freq // 8) * 64)
    freq_dim = input_shape[0] // (2 ** len(filters_list))
    feat_dim = freq_dim * filters_list[-1]
    time_dim = input_shape[1]
    x = tf.keras.layers.Reshape((time_dim, feat_dim))(x)

    # 2. Bidirectional recurrent temporal modeling
    gru_units = int(config.get("crnn_gru_units", 64))
    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.GRU(gru_units, return_sequences=True)
    )(x)

    # 3. Regularization & Time-distributed frame classification
    dropout_rate = float(config.get("cnn_dropout", 0.30))
    x = tf.keras.layers.Dropout(dropout_rate)(x)

    # Output: (batch, time_frames, 1) with sigmoid per frame
    outputs = tf.keras.layers.TimeDistributed(
        tf.keras.layers.Dense(1, activation="sigmoid"),
        name="frame_probability",
    )(x)

    model = tf.keras.Model(inputs, outputs, name="auriscore_abdomen_crnn_sed")

    # 4. Compilation with focal loss for handling class imbalance (silence > burst)
    loss_kind = str(config.get("cnn_loss", "focal"))
    if loss_kind == "focal":
        loss = tf.keras.losses.BinaryFocalCrossentropy(gamma=2.0, apply_class_balancing=False)
    else:
        loss = tf.keras.losses.BinaryCrossentropy()

    lr = float(config.get("cnn_learning_rate", 1e-3))
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
        loss=loss,
        metrics=[
            tf.keras.metrics.BinaryAccuracy(name="accuracy"),
            tf.keras.metrics.Recall(name="sensitivity"),
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.AUC(name="roc_auc"),
            tf.keras.metrics.AUC(name="pr_auc", curve="PR"),
        ],
    )
    return model
