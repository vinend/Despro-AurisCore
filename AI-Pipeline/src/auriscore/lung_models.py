"""Independent Lung heads; TensorFlow imported only when explicitly needed."""
import numpy as np


def build_model(shape, classes, *, temporal=True, learning_rate=.001, positive_weights=None, dropout=.2):
    """Time-preserving compact CNN; optional pooled window research baseline."""
    from .lung_training_policy import validate_dropout
    dropout = validate_dropout(dropout)
    import tensorflow as tf
    if len(shape) != 2 or min(shape) < 1 or not classes:
        raise ValueError("Expected time/frequency dimensions and explicit classes")
    inputs = tf.keras.Input(shape=shape, name="lung_logmel")
    x = tf.keras.layers.Reshape((*shape, 1))(inputs)
    for width in (16, 32, 64):
        x = tf.keras.layers.Conv2D(width, (3, 3), padding="same", activation="relu")(x)
        x = tf.keras.layers.MaxPooling2D((1, 2))(x)
    # Pool frequency only, keeping every output frame aligned with its input.
    x = tf.keras.layers.Reshape((shape[0], int(x.shape[2]) * int(x.shape[3])))(x)
    x = tf.keras.layers.Conv1D(64, 5, padding="same", activation="relu")(x)
    x = tf.keras.layers.Dropout(dropout)(x)
    if not temporal:
        x = tf.keras.layers.GlobalAveragePooling1D()(x)
    outputs = tf.keras.layers.Dense(len(classes), activation="sigmoid", name="lung_probabilities")(x)
    model = tf.keras.Model(inputs, outputs, name="lung_temporal_cnn" if temporal else "lung_window_cnn")
    weights = np.ones(len(classes), np.float32) if positive_weights is None else np.asarray(positive_weights, np.float32)
    if weights.shape != (len(classes),) or not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("Invalid class weights")

    def masked_loss(packed, predicted):
        truth, mask = packed[..., :len(classes)], packed[..., len(classes):]
        predicted = tf.clip_by_value(predicted, 1e-7, 1 - 1e-7)
        loss = -(truth * tf.math.log(predicted) * weights + (1 - truth) * tf.math.log(1 - predicted))
        axes = tuple(range(1, len(loss.shape)))
        return tf.reduce_sum(loss * mask, axis=axes) / tf.maximum(tf.reduce_sum(mask, axis=axes), 1.)
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate), loss=masked_loss)
    return model
