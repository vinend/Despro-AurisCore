from pathlib import Path
import pytest
from auriscore.config import load_config


@pytest.fixture
def config():
    return load_config(Path(__file__).resolve().parents[1] / "configs/heart_baseline.yaml")
