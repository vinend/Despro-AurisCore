"""Independent Lung heads; TensorFlow imported only when explicitly needed."""
import numpy as np


def build_model(shape, classes, *, temporal=True, learning_rate=.001, positive_weights=None, dropout=.2, temporal_dilation=1, weight_decay=0., bottleneck_channels=None, loss_numerics='legacy_clip', multiscale_temporal=False, temporal_delta=False):
    """Time-preserving compact CNN; optional pooled window research baseline."""
    from .lung_training_policy import validate_dropout, model_dilation, model_bottleneck
    dropout = validate_dropout(dropout)
    temporal_dilation = model_dilation({"model": {"temporal_dilation": temporal_dilation}})
    bottleneck_channels = model_bottleneck({'model': {'bottleneck_channels': bottleneck_channels}})
    if (isinstance(weight_decay, bool) or not isinstance(weight_decay, (int, float))
            or not np.isfinite(weight_decay) or not 0 <= weight_decay <= .01):
        raise ValueError("Invalid Lung weight decay")
    import tensorflow as tf
    if loss_numerics not in ('legacy_clip', 'stable_bce'):
        raise ValueError('Unknown Lung loss numerics')
    if len(shape) != 2 or min(shape) < 1 or not classes:
        raise ValueError("Expected time/frequency dimensions and explicit classes")
    inputs = tf.keras.Input(shape=shape, name="lung_logmel")
    x = tf.keras.layers.Reshape((*shape, 1))(inputs)
    if temporal_delta:
        previous = tf.keras.layers.Cropping2D(cropping=((0, 1), (0, 0)))(x)
        current = tf.keras.layers.Cropping2D(cropping=((1, 0), (0, 0)))(x)
        delta = tf.keras.layers.Subtract()([current, previous])
        delta = tf.keras.layers.ZeroPadding2D(padding=((1, 0), (0, 0)))(delta)
        x = tf.keras.layers.Concatenate(name="logmel_with_delta")([x, delta])
    for width in (16, 32, 64):
        x = tf.keras.layers.Conv2D(width, (3, 3), padding="same", activation="relu")(x)
        x = tf.keras.layers.MaxPooling2D((1, 2))(x)
    # Pool frequency only, keeping every output frame aligned with its input.
    x = tf.keras.layers.Reshape((shape[0], int(x.shape[2]) * int(x.shape[3])))(x)
    if bottleneck_channels is not None:
        x = tf.keras.layers.Conv1D(bottleneck_channels, 1, padding='same', activation='relu', name='frequency_bottleneck')(x)
    if multiscale_temporal:
        short = tf.keras.layers.Conv1D(32, 5, padding="same", activation="relu",
                                       name="temporal_local")(x)
        long = tf.keras.layers.Conv1D(32, 5, padding="same", dilation_rate=temporal_dilation,
                                      activation="relu", name="temporal_context")(x)
        x = tf.keras.layers.Concatenate(name="temporal_multiscale")([short, long])
    else:
        x = tf.keras.layers.Conv1D(64, 5, padding="same", dilation_rate=temporal_dilation, activation="relu")(x)
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
        if loss_numerics == 'stable_bce':
            # Public Keras BCE retains the sigmoid's logits for stable gradients.
            loss = tf.keras.ops.binary_crossentropy(truth, predicted, from_logits=False)
            loss = loss * (1 - truth + truth * weights)
        else:
            predicted = tf.clip_by_value(predicted, 1e-7, 1 - 1e-7)
            loss = -(truth * tf.math.log(predicted) * weights + (1 - truth) * tf.math.log(1 - predicted))
        axes = tuple(range(1, len(loss.shape)))
        return tf.reduce_sum(loss * mask, axis=axes) / tf.maximum(tf.reduce_sum(mask, axis=axes), 1.)
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate, weight_decay=weight_decay or None), loss=masked_loss)
    return model
