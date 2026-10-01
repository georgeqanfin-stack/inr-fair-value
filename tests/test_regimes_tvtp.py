import numpy as np
import pandas as pd
import pytest

from inrfv.models import regimes_tvtp as rt


def test_drivers_are_lagged_one_month():
    idx = pd.date_range("2020-01-01", periods=4, freq="MS")
    pit = pd.DataFrame({"vix": [10.0, 12, 15, 11], "brent": [50.0, 55, 60, 50], "fpi_usd_mn": [1000.0, -2000, 3000, 0],
                        "rbi_intervention_usd_mn": [0.0, -5000, 0, 1000]}, index=idx)
    d = rt.drivers(pit)
    assert np.isnan(d.loc[idx[1], "vix"]) and d.loc[idx[2], "vix"] == 2.0      # change Jan->Feb used in Mar
    assert d.loc[idx[2], "fpi"] == -2.0 and d.loc[idx[3], "rbi"] == 0.0


def test_newey_west_t_of_a_mean():
    x = np.r_[np.full(50, 1.0), np.full(50, 3.0)] + np.random.default_rng(0).normal(0, 0.01, 100)
    assert rt._nw_t(x) > 5
    assert abs(rt._nw_t(np.random.default_rng(1).normal(0, 1, 400))) < 3


def test_auc():
    s = pd.Series([0.9, 0.8, 0.2, 0.1])
    assert rt._auc(s, pd.Series([True, True, False, False])) == 1.0
    assert rt._auc(s, pd.Series([False, False, True, True])) == 0.0


def test_tvtp_fit_beats_constant_when_a_driver_drives_switching():
    rng = np.random.default_rng(5)
    n = 400
    z = rng.normal(0, 1, n)
    s = np.zeros(n, dtype=int)
    for t in range(1, n):
        p_stress = 1 / (1 + np.exp(-(-2.5 + 2.5 * z[t])))
        s[t] = rng.random() < (p_stress if s[t - 1] == 0 else 0.6)
    r = np.where(s == 1, rng.normal(0, 3, n), rng.normal(0, 0.5, n))
    _, c, _ = rt.fit(r, None, 1)
    _, v, _ = rt.fit(r, z[:, None], 1)
    assert v.llf > c.llf + 5
