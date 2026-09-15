from pathlib import Path

import pytest

from cyberpnl.models import load_model

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def model():
    return load_model(ROOT / "model")
