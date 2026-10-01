import numpy as np
import pandas as pd
import pytest

from inrfv import backtest
from inrfv.models import nonlinear


def test_threshold_finds_faster_reversion_outside_the_band(rng):
    e = rng.normal(0, 0.1, 600)
    y = np.where(np.abs(e) > 0.1, -0.5 * e, 0.0) + rng.normal(0, 0.005, 600)
    _, par = nonlinear.fit_threshold(e, y, 0.0)
    assert par["b_out"] == pytest.approx(-0.5, abs=0.1) and abs(par["b_in"]) < 0.2


def test_cubic_recovers_the_cubic_term(rng):
    e = rng.normal(0, 0.2, 800)
    y = 0.01 - 0.1 * e - 2.0 * e ** 3 + rng.normal(0, 0.002, 800)
    _, par = nonlinear.fit_cubic(e, y, 0.0)
    assert par["g"] == pytest.approx(-2.0, abs=0.2)


def test_tvp_follows_a_shift_in_the_slope(rng):
    e = rng.normal(0, 0.1, 400)
    b = np.where(np.arange(400) < 200, -0.1, -0.8)
    y = b * e + rng.normal(0, 0.005, 400)
    _, par = nonlinear.fit_tvp(e, y, 0.0)
    assert par["b"] == pytest.approx(-0.8, abs=0.15)


def test_break_test_detects_a_mean_shift_and_not_a_fake_one(rng):
    idx = pd.date_range("2000-01-01", periods=240, freq="MS")
    x = pd.DataFrame({"const": 1.0}, index=idx)
    shifted = pd.Series(np.where(np.arange(240) < 150, 0.0, 2.0) + rng.normal(0, 0.5, 240), idx)
    flat = pd.Series(rng.normal(0, 0.5, 240), idx)
    hit = nonlinear.break_test(shifted, x, 49, 12, np.random.default_rng(1))
    none = nonlinear.break_test(flat, x, 49, 12, np.random.default_rng(1))
    assert hit["p"] < 0.05 and abs(idx.get_loc(pd.Timestamp(hit["date"] + "-01")) - 150) <= 3
    assert none["p"] > 0.05


def test_rolling_window_matches_backtest(rng):
    idx = pd.date_range("2000-01-01", periods=200, freq="MS")
    comp = pd.DataFrame({"log_inr": np.cumsum(rng.normal(0, 0.02, 200)), "ect": rng.normal(0, 0.1, 200)}, idx)
    a = backtest.forecasts(comp, 3, 60, window=48)
    b = nonlinear.forecasts(comp, 3, 60, nonlinear.fit_linear, window=48)
    np.testing.assert_allclose(a["f_ecm"], b["f_ecm"])
    np.testing.assert_allclose(a["f_drift"], b["f_drift"])
