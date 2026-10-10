"""Training-only Lung schedules, independent of immutable feature cache geometry."""
import json
from pathlib import Path
from typing import Any

import numpy as np

POLICY_SCHEMA = "lung-training-policy-v1"
MODEL_POLICY_SCHEMA = "lung-training-policy-v2"


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
    required = {"schema_version", "learning_rate_schedule"}
    if version == MODEL_POLICY_SCHEMA:
        required.add("model")
    if (version not in {POLICY_SCHEMA, MODEL_POLICY_SCHEMA} or set(policy) != required
            or not isinstance(policy["learning_rate_schedule"], dict)):
        raise ValueError("Invalid Lung training policy schema")
    if version == MODEL_POLICY_SCHEMA:
        if not isinstance(policy["model"], dict) or set(policy["model"]) != {"dropout"}:
            raise ValueError("Explicit dropout-only model policy required")
        model_dropout(policy)
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
