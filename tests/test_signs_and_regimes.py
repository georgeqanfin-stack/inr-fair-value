import numpy as np
import pandas as pd
import pytest

from inrfv.models import composite, feer, regimes, structural


def test_reer_below_trend_means_inr_undervalued(cfg):
    idx = pd.date_range("2000-01-01", periods=120, freq="MS")
    reer = pd.Series(100.0, index=idx)
    reer.iloc[-1] = 90.0                        # sharp real depreciation in the last month
    pit = pd.DataFrame({"reer": reer, "inr_usd": 80.0}, index=idx)
    out = structural.run(pit, cfg)
    assert out["misalignment_pct"].iloc[-1] > 0
    assert out["fair_inr"].iloc[-1] < 80.0       # fair value is a stronger rupee


def test_feer_sign(cfg):
    idx = pd.date_range("2010-01-01", periods=60, freq="MS")
    pit = pd.DataFrame({"brent": 70.0, "inr_usd": 80.0}, index=idx)
    q = pd.date_range("2010-01-01", periods=12, freq="QS-JAN")
    bop = pd.DataFrame({"available": q + pd.offsets.MonthBegin(6),
                        "current_account_pct_gdp": 0.5,     # surplus: far better than the -2.5% norm
                        "brent_q": 70.0, "inr_q": 80.0, "fdi_bop": 1.0, "loans": 1.0, "gdp_usd_mn": 1.0},
                       index=q)
    cfg["models"]["feer"]["oil_elasticity"] = -2.0
    fq, _ = feer.run(bop, pit, cfg)
    assert (fq["misalignment_pct"] > 0).all()   # room to appreciate -> INR undervalued
    assert (fq["fair_inr_q"] < 80.0).all()


def test_composite_fair_below_spot_when_ect_positive(cfg):
    idx = pd.date_range("2010-01-01", periods=3, freq="MS")
    pit = pd.DataFrame({"inr_usd": 90.0, "log_inr": np.log(90.0)}, index=idx)
    comp = composite.run(pit, pd.DataFrame({"gap_log": 0.1}, index=idx),
                         pd.DataFrame({"gap_log": 0.1}, index=idx), cfg)
    assert (comp["fair_inr"] < 90).all()
    assert comp["misalignment_pct"].iloc[0] == pytest.approx((np.exp(0.1) - 1) * 100)


class _FakeRes:
    # statsmodels layout: regime_transition[to, from, 0]
    regime_transition = np.array([[[0.876], [0.272]], [[0.124], [0.728]]])


def test_transition_matrix_orientation():
    P = regimes.row_stochastic(_FakeRes())
    assert np.allclose(P.sum(axis=1), 1)
    assert P[0, 1] == pytest.approx(0.124)       # calm -> stress
    assert P[1, 0] == pytest.approx(0.272)       # stress -> calm


def test_stress_forecast_converges_to_steady_state():
    P = regimes.row_stochastic(_FakeRes())
    fc = regimes.stress_forecast(P, np.array([0.902, 0.098]), horizons=(3, 12, 240))
    steady = 0.124 / (0.124 + 0.272)
    assert fc[240][1] == pytest.approx(steady, abs=1e-6)
    assert fc[12][1] == pytest.approx(0.313, abs=0.005)   # legacy notebook reported 0.648


def test_stress_forecast_rejects_legacy_matrix():
    legacy = np.array([[0.876, 0.272], [0.124, 0.728]])  # rows sum to 1.148 / 0.852
    with pytest.raises(ValueError):
        regimes.stress_forecast(legacy, np.array([0.9, 0.1]))
