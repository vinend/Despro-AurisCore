"""Three acoustic outputs preserve cache column identity and independent labels."""
import json
from pathlib import Path
import pytest
import yaml
from auriscore.lung_training_policy import load_policy, selected_classes

ROOT = Path(__file__).parents[1]


def test_three_sound_changes_only_selected_classes_relative_to_l011():
    config = yaml.safe_load((ROOT / 'configs/lung_cnn.yaml').read_text())
    original = load_policy(ROOT / 'configs/lung_training_sound_only.json', config)
    selected = load_policy(ROOT / 'configs/lung_training_three_sound.json', config)
    assert selected_classes(selected, config) == ['wheeze', 'rhonchi', 'crackle']
    assert [config['classes'].index(c) for c in selected['classes']] == [2, 3, 5]
    assert {k: v for k, v in original.items() if k != 'classes'} == {k: v for k, v in selected.items() if k != 'classes'}
    plan = json.loads((ROOT / 'configs/lung_three_sound_queue.json').read_text())
    assert plan['baseline'] == 'EXP-L011-sound-only'


def test_three_sound_model_is_time_preserving_multilabel():
    tf = pytest.importorskip('tensorflow')
    from auriscore.lung_models import build_model
    model = build_model((309, 96), ['wheeze', 'rhonchi', 'crackle'], temporal_dilation=16)
    assert model.output_shape == (None, 309, 3)
    assert model.count_params() == 269315
    assert model.layers[-1].activation == tf.keras.activations.sigmoid
    assert int(model.optimizer.iterations.numpy()) == 0
