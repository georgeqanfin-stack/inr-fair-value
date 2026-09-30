from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inrfv.config import load_config

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def months():
    return pd.date_range("2000-01-01", periods=240, freq="MS")


@pytest.fixture
def rng():
    return np.random.default_rng(0)
