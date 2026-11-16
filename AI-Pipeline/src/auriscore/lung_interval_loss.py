"""Research objective for positive runs in the Lung frame annotations."""


def interval_loss(positive_weights):
    """Use the best frame in each positive run, keeping known negatives framewise.

    Each run retains its original frame mass so the comparison changes only
    which scores drive positive BCE. Unknown frames terminate positive runs.
    """
    import tensorflow as tf

    weights = tf.constant(positive_weights, dtype=tf.float32)
    classes = len(positive_weights)

    def masked_interval_bce(packed, predicted):
        truth, mask = packed[..., :classes], packed[..., classes:]
        point_loss = tf.keras.ops.binary_crossentropy(truth, predicted)
        known_positive = (truth > 0) & (mask > 0)
        positive = tf.transpose(known_positive, [0, 2, 1])
        previous = tf.concat([tf.zeros_like(positive[..., :1]), positive[..., :-1]], axis=-1)
        shape = tf.shape(positive)
        stride = shape[2] + 1
        offsets = tf.reshape(tf.range(shape[0] * shape[1]) * stride, [shape[0], shape[1], 1])
        runs = tf.cumsum(tf.cast(positive & ~previous, tf.int32), axis=-1)
        segments = tf.reshape(offsets + tf.where(positive, runs, 0), [-1])
        count = shape[0] * shape[1] * stride
        loss = tf.reshape(tf.transpose(point_loss, [0, 2, 1]), [-1])
        minimum = tf.math.unsorted_segment_min(loss, segments, count)
        pooled = tf.transpose(tf.reshape(tf.gather(minimum, segments), shape), [0, 2, 1])
        weighted = tf.where(known_positive, pooled * weights, point_loss)
        return tf.math.divide_no_nan(
            tf.reduce_sum(weighted * mask, axis=[1, 2]), tf.reduce_sum(mask, axis=[1, 2])
        )

    return masked_interval_bce
