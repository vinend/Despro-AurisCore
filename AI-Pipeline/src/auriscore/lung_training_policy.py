"""Training-only Lung schedules, independent of immutable feature cache geometry."""
import json
from pathlib import Path
from typing import Any

import numpy as np

POLICY_SCHEMA = "lung-training-policy-v1"
MODEL_POLICY_SCHEMA = "lung-training-policy-v2"
CONTEXT_POLICY_SCHEMA = "lung-training-policy-v3"
RESEARCH_POLICY_SCHEMA = "lung-training-policy-v4"
COMPACT_POLICY_SCHEMA = "lung-training-policy-v5"
OBJECTIVE_POLICY_SCHEMA = "lung-training-policy-v6"
TRAJECTORY_POLICY_SCHEMA = "lung-training-policy-v7"
OBJECTIVE_SCHEMAS = (OBJECTIVE_POLICY_SCHEMA, TRAJECTORY_POLICY_SCHEMA)


def loss_settings(policy: dict) -> dict:
    """Resolve opt-in loss changes; historical policies retain their exact objective."""
    return dict(policy.get('loss', {'numerics': 'legacy_clip',
                                   'positive_weighting': 'global_frame',
                                   'empty_training_windows': 'keep'}))


def model_bottleneck(policy: dict) -> int | None:
    """Resolve an opt-in time-preserving frequency-feature projection."""
    value = policy.get('model', {}).get('bottleneck_channels')
    if value is not None and (type(value) is not int or value not in (8, 16, 32, 64, 128)):
        raise ValueError('Bottleneck channels must be one of 8, 16, 32, 64, 128')
    return value


def optimizer_settings(policy: dict, config: dict) -> tuple[float, float]:
    """Resolve opt-in optimizer changes without mutating cached preprocessing."""
    settings = policy.get("optimizer", {})
    return float(settings.get("initial_learning_rate", config["learning_rate"])), float(settings.get("weight_decay", 0))


def selected_classes(policy: dict, config: dict) -> list[str]:
    """Select an ordered research head; never infer absent labels for other tasks."""
    return list(policy.get("classes") or config["classes"])


def frequency_mask_bins(policy: dict) -> int:
    """Maximum TRAIN-only normalized-feature frequency mask width."""
    return policy.get("augmentation", {}).get("frequency_mask_bins", 0)


def model_dilation(policy: dict) -> int:
    """Resolve the frozen temporal dilation; historical models use one."""
    value = policy.get("model", {}).get("temporal_dilation", 1)
    if type(value) is not int or not 1 <= value <= 16:
        raise ValueError("Temporal dilation must be an integer from 1 to 16")
    return value


def validate_dropout(value: float) -> float:
    """Accept a finite numeric dropout probability; reject bools and silent coercion."""
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not np.isfinite(value) or not 0 <= value < 1):
        raise ValueError("Lung dropout must be a finite number in [0, 1)")
    return float(value)


def model_dropout(policy: dict) -> float:
    """Resolve explicit v2 dropout or the historical v1/default rate of 0.2."""
    return validate_dropout(policy.get("model", {"dropout": .2})["dropout"])


def validate_policy(policy: dict, config: dict) -> dict:
    """Validate a closed training policy without importing TensorFlow or changing data."""
    initial = config.get("learning_rate")
    if (isinstance(initial, bool) or not isinstance(initial, (int, float))
            or not np.isfinite(initial) or initial <= 0):
        raise ValueError("Positive finite cached learning rate required")
    if not isinstance(policy, dict):
        raise ValueError("Invalid Lung training policy schema")
    version = policy.get("schema_version")
    if version == TRAJECTORY_POLICY_SCHEMA:
        base = {k: v for k, v in policy.items() if k != 'trajectory'}
        base['schema_version'] = OBJECTIVE_POLICY_SCHEMA
        validate_policy(base, config)
        trajectory = policy.get('trajectory')
        if (not isinstance(trajectory, dict)
                or set(trajectory) != {'every_epochs', 'recordings_per_device_partition', 'thresholds'}
                or type(trajectory['every_epochs']) is not int or trajectory['every_epochs'] != 1
                or type(trajectory['recordings_per_device_partition']) is not int
                or not 1 <= trajectory['recordings_per_device_partition'] <= 64
                or not isinstance(trajectory['thresholds'], list)
                or len(trajectory['thresholds']) != len(selected_classes(base, config))
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v)
                       or not 0 < v < 1 for v in trajectory['thresholds'])):
            raise ValueError('Explicit bounded per-epoch trajectory policy required')
        return json.loads(json.dumps(policy, allow_nan=False))
    if version == OBJECTIVE_POLICY_SCHEMA:
        # Reuse the closed noncompact v4 schema before validating the new boundary.
        if 'loss' not in policy or policy.get('runtime') != {'deterministic_ops': True, 'tf32': False}:
            raise ValueError('Explicit loss and deterministic float32 runtime required')
        if (type(policy['runtime']['deterministic_ops']) is not bool
                or type(policy['runtime']['tf32']) is not bool):
            raise ValueError('Runtime flags must be explicit booleans')
        legacy = {k: v for k, v in policy.items() if k not in ('loss', 'runtime')}
        legacy['schema_version'] = RESEARCH_POLICY_SCHEMA
        validate_policy(legacy, config)
        loss = policy['loss']
        if (not isinstance(loss, dict)
                or set(loss) != {'numerics', 'positive_weighting', 'empty_training_windows'}
                or loss['numerics'] != 'stable_bce'
                or loss['positive_weighting'] not in ('global_frame', 'window_mass')
                or loss['empty_training_windows'] not in ('keep', 'drop')):
            raise ValueError('Invalid versioned Lung loss policy')
        return json.loads(json.dumps(policy, allow_nan=False))
    required = {"schema_version", "learning_rate_schedule"}
    if version in (MODEL_POLICY_SCHEMA, CONTEXT_POLICY_SCHEMA, RESEARCH_POLICY_SCHEMA, COMPACT_POLICY_SCHEMA):
        required.add("model")
    if version in (RESEARCH_POLICY_SCHEMA, COMPACT_POLICY_SCHEMA):
        required.update({"optimizer", "augmentation", "classes"})
    if (version not in (POLICY_SCHEMA, MODEL_POLICY_SCHEMA, CONTEXT_POLICY_SCHEMA, RESEARCH_POLICY_SCHEMA, COMPACT_POLICY_SCHEMA) or set(policy) != required
            or not isinstance(policy["learning_rate_schedule"], dict)):
        raise ValueError("Invalid Lung training policy schema")
    if version in (MODEL_POLICY_SCHEMA, CONTEXT_POLICY_SCHEMA, RESEARCH_POLICY_SCHEMA, COMPACT_POLICY_SCHEMA):
        model_keys = {"dropout", "temporal_dilation"} if version != MODEL_POLICY_SCHEMA else {"dropout"}
        if version == COMPACT_POLICY_SCHEMA:
            model_keys.add('bottleneck_channels')
        if not isinstance(policy["model"], dict) or set(policy["model"]) != model_keys:
            raise ValueError("Explicit versioned model policy required")
        model_dropout(policy)
        model_dilation(policy)
        if version == COMPACT_POLICY_SCHEMA and model_bottleneck(policy) is None:
            raise ValueError('Compact policy requires explicit bottleneck channels')
    if version in (RESEARCH_POLICY_SCHEMA, COMPACT_POLICY_SCHEMA):
        optimizer = policy["optimizer"]
        augmentation = policy["augmentation"]
        if (not isinstance(optimizer, dict) or set(optimizer) != {"initial_learning_rate", "weight_decay"}
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v)
                       for v in optimizer.values())
                or not 0 < optimizer["initial_learning_rate"] <= initial
                or not 0 <= optimizer["weight_decay"] <= .01):
            raise ValueError("Invalid research optimizer policy")
        if (not isinstance(augmentation, dict) or set(augmentation) != {"frequency_mask_bins"}
                or type(augmentation["frequency_mask_bins"]) is not int
                or not 0 <= augmentation["frequency_mask_bins"] <= min(8, config.get("n_mels", 96))):
            raise ValueError("Invalid TRAIN frequency mask policy")
        classes = policy["classes"]
        if classes is not None and (not isinstance(classes, list) or not classes
                or any(not isinstance(c, str) for c in classes) or len(set(classes)) != len(classes)
                or classes != [c for c in config["classes"] if c in classes]):
            raise ValueError("Research classes must be a unique ordered cache subset")
        initial, _ = optimizer_settings(policy, config)
    schedule = policy["learning_rate_schedule"]
    if schedule == {"type": "constant"}:
        return json.loads(json.dumps(policy))
    keys = {"type", "monitor", "factor", "patience", "min_delta", "cooldown", "min_lr"}
    if set(schedule) != keys or schedule["type"] != "reduce_on_plateau" or schedule["monitor"] != "val_loss":
        raise ValueError("Only explicit val_loss plateau or constant schedules are supported")
    for key in ("factor", "min_delta", "min_lr"):
        value = schedule[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError("Finite numeric plateau settings required")
    if (not 0 < schedule["factor"] < 1 or schedule["min_delta"] < 0
            or not 0 < schedule["min_lr"] < initial
            or type(schedule["patience"]) is not int or schedule["patience"] < 1
            or type(schedule["cooldown"]) is not int or schedule["cooldown"] < 0
            or type(config.get("patience")) is not int
            or schedule["patience"] + schedule["cooldown"] >= config["patience"]):
        raise ValueError("Plateau reduction must occur before early stopping with a lower positive LR floor")
    return json.loads(json.dumps(policy, allow_nan=False))


def load_policy(path: Path | None, config: dict) -> dict:
    """Resolve an opt-in policy; omission reproduces the fixed-LR baseline."""
    policy = (json.loads(Path(path).read_text()) if path is not None else
              {"schema_version": POLICY_SCHEMA, "learning_rate_schedule": {"type": "constant"}})
    return validate_policy(policy, config)


def learning_rate_logger() -> Any:
    """Record LR used during an epoch and LR scheduled for the following epoch."""
    import tensorflow as tf

    class EpochLearningRate(tf.keras.callbacks.Callback):
        def on_epoch_begin(self, epoch, logs=None):
            self.used = float(tf.keras.backend.get_value(self.model.optimizer.learning_rate))

        def on_epoch_end(self, epoch, logs=None):
            if logs is not None:
                logs["learning_rate"] = self.used
                logs["next_learning_rate"] = float(tf.keras.backend.get_value(self.model.optimizer.learning_rate))

    return EpochLearningRate()


def development_callbacks(folder: Path, config: dict, policy: dict) -> list[Any]:
    """Reduce LR before the recorder/stopper; retain restored-best checkpoint semantics."""
    import tensorflow as tf
    validate_policy(policy, config)
    schedule = policy["learning_rate_schedule"]
    callbacks = []
    if schedule["type"] == "reduce_on_plateau":
        callbacks.append(tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", mode="min", factor=schedule["factor"], patience=schedule["patience"],
            min_delta=schedule["min_delta"], cooldown=schedule["cooldown"], min_lr=schedule["min_lr"], verbose=1))
    callbacks.extend([learning_rate_logger(),
                      tf.keras.callbacks.EarlyStopping(monitor="val_loss", mode="min", patience=config["patience"], restore_best_weights=True),
                      tf.keras.callbacks.CSVLogger(str(folder / "history.csv")),
                      tf.keras.callbacks.ModelCheckpoint(str(folder / "best.weights.h5"), monitor="val_loss", mode="min",
                                                         save_weights_only=True, save_best_only=True)])
    return callbacks


def final_learning_rates(selection: dict, config: dict) -> tuple[dict, list[float] | None]:
    """Require frozen epoch rates to replay a selected development plateau run.

    All-development final fitting has no validation callbacks; never monitor test
    data or silently replace an adaptive development protocol with constant LR.
    """
    policy = (validate_policy(selection["training_policy"], config) if "training_policy" in selection
              else load_policy(None, config))
    config = {**config, "learning_rate": optimizer_settings(policy, config)[0]}
    rates = selection.get("learning_rates")
    if rates is None:
        if policy["learning_rate_schedule"]["type"] != "constant":
            raise ValueError("Final plateau selection requires frozen learning_rates from development history")
        return policy, None
    if (type(selection.get("epochs")) is not int or selection["epochs"] < 1
            or not isinstance(rates, list) or len(rates) != selection["epochs"]
            or any(isinstance(rate, bool) or not isinstance(rate, (int, float)) or not np.isfinite(rate)
                   or not 0 < rate <= config["learning_rate"] * (1 + 1e-6) for rate in rates)
            or any(after > before * (1 + 1e-6) for before, after in zip(rates, rates[1:]))
            or not np.isclose(rates[0], config["learning_rate"], rtol=1e-6, atol=0)):
        raise ValueError("Frozen epoch rates must start at cached LR and remain finite, positive and nonincreasing")
    schedule = policy["learning_rate_schedule"]
    if schedule["type"] == "constant" and not np.allclose(rates, config["learning_rate"], rtol=1e-6, atol=0):
        raise ValueError("Constant policy cannot replay varying epoch rates")
    if schedule["type"] == "reduce_on_plateau" and min(rates) < schedule["min_lr"] * (1 - 1e-6):
        raise ValueError("Frozen rates cannot fall below the selected policy floor")
    return policy, [float(rate) for rate in rates]
