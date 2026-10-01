import numpy as np
import pandas as pd
import pytest

from inrfv.data.build import _one_sided_hp_gap
from inrfv.models import feer


def test_semi_elasticity_income_term_sign():
    trade = feer.semi(20.0, 24.0, -1.2, 0.46, 0.25, 0.0)
    with_inc = feer.semi(20.0, 24.0, -1.2, 0.46, 0.25, 0.5)
    assert trade == pytest.approx(-(0.46 * 20 + 0.25 * 24) / 100)
    assert with_inc == pytest.approx(trade + 0.5 * 1.2 / 100)          # deficit -> smaller in absolute value
    assert feer.semi(20.0, 24.0, np.nan, 0.46, 0.25, 0.5) == pytest.approx(trade)


def test_one_sided_gap_uses_only_past_data():
    idx = pd.date_range("2000-01-01", periods=60, freq="QS")
    s = pd.Series(np.log(100) + 0.01 * np.arange(60) + 0.02 * np.sin(np.arange(60) / 3), idx)
    g = _one_sided_hp_gap(s)
    s2 = s.copy()
    s2.iloc[40:] += 0.5                                                 # a later shock
    g2 = _one_sided_hp_gap(s2)
    pd.testing.assert_series_equal(g.loc[: idx[39]], g2.loc[: idx[39]])


def test_cyclical_adjustment_raises_underlying_ca_when_india_runs_hot(cfg):
    p = dict(cfg["models"]["feer"])
    idx = pd.date_range("2020-01-01", periods=8, freq="QS")
    q = pd.DataFrame({"output_gap_india": 2.0, "output_gap_partners": 0.5}, index=idx)
    rel = q["output_gap_india"] - q["output_gap_partners"]
    contrib = p["cyclical_coefficient"] * rel
    assert (contrib < 0).all() and contrib.iloc[0] == pytest.approx(-0.3564 * 1.5)
