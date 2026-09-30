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


def _flat_bop(q, ca_pct, gdp=3e6, **extra):
    df = pd.DataFrame({"available": q + pd.offsets.MonthBegin(6), "gdp_usd_mn": gdp,
                       "current_account": ca_pct / 100 * gdp / 4, "inr_q": 80.0,
                       "fdi_bop": 1.0, "loans": 1.0}, index=q)
    for k, v in extra.items():
        df[k] = v
    return df


GROSS = {"goods_credit": 1.2e5, "services_credit": 0.45e5, "goods_debit": 1.5e5, "services_debit": 0.3e5}


def test_feer_sign(cfg):
    idx = pd.date_range("2005-01-01", periods=120, freq="MS")
    pit = pd.DataFrame({"brent": 70.0, "inr_usd": 80.0}, index=idx)
    q = pd.date_range("2005-01-01", periods=36, freq="QS-JAN")
    fq, _ = feer.run(_flat_bop(q, 0.5, **GROSS), pit, cfg)   # surplus: far better than any norm
    ok = fq["misalignment_pct"].dropna()
    assert len(ok) and (ok > 0).all()                         # room to appreciate -> INR undervalued
    assert (fq["fair_inr_q"].dropna() < 80.0).all()


def test_feer_semi_elasticity_follows_eba_formula(cfg):
    idx = pd.date_range("2005-01-01", periods=120, freq="MS")
    pit = pd.DataFrame({"brent": 70.0, "inr_usd": 80.0}, index=idx)
    q = pd.date_range("2005-01-01", periods=12, freq="QS-JAN")
    fq, _ = feer.run(_flat_bop(q, -1.0, **GROSS), pit, cfg)
    p = cfg["models"]["feer"]
    x = (1.2e5 + 0.45e5) * 4 / 3e6 * 100          # 22% of GDP
    m = (1.5e5 + 0.3e5) * 4 / 3e6 * 100           # 24% of GDP
    assert fq["semi_elasticity"].iloc[-1] == pytest.approx(-(p["eta_exports"] * x + p["eta_imports"] * m) / 100)
    assert fq["exports_pct_gdp"].iloc[-1] == pytest.approx(x)
    # Without gross flows the configured fallback is used and labelled.
    fq2, _ = feer.run(_flat_bop(q, -1.0), pit, cfg)
    assert (fq2["semi_elasticity"] == p["fallback_semi_elasticity"]).all()
    assert (fq2["semi_source"] == "fallback").all()


def test_feer_oil_adjustment_sign(cfg):
    idx = pd.date_range("2000-01-01", periods=120, freq="MS")
    brent = pd.Series(60.0, index=idx)
    brent.iloc[-12:] = 120.0                                  # oil spike over the last year
    pit = pd.DataFrame({"brent": brent, "inr_usd": 80.0}, index=idx)
    q = pd.date_range("2000-01-01", periods=40, freq="QS-JAN")
    fq, _ = feer.run(_flat_bop(q, -2.0, net_oil_imports=2.5e4, **GROSS), pit, cfg)
    last = fq.iloc[-1]
    assert last["oil_adjustment"] > 0                         # expensive oil depresses the actual CA
    assert last["cad_underlying"] > last["ca_pct_4q"]
    assert last["oil_adjustment"] == pytest.approx(last["net_oil_pct_gdp"] * (1 - last["brent_norm"] / last["brent_paid"]))


def test_feer_niip_norm(cfg):
    idx = pd.date_range("2000-01-01", periods=180, freq="MS")
    pit = pd.DataFrame({"brent": 70.0, "inr_usd": 80.0}, index=idx)
    q = pd.date_range("2000-01-01", periods=60, freq="QS-JAN")
    gdp = 1e6 * 1.10 ** (np.arange(60) / 4)                  # 10% a year nominal US$ growth
    bop = _flat_bop(q, -1.0, gdp=gdp, niip=-0.10 * gdp, **{k: v * gdp / 3e6 for k, v in GROSS.items()})
    fq, _ = feer.run(bop, pit, cfg)
    # NIIP/GDP = -10% and g = 10%: stabilising CA = -10 * 0.1 / 1.1 = -0.91% of GDP.
    assert fq["norm_niip"].iloc[-1] == pytest.approx(-10 * 0.1 / 1.1, abs=0.02)


def test_feer_band_is_ordered_and_brackets_central(cfg):
    idx = pd.date_range("2005-01-01", periods=120, freq="MS")
    pit = pd.DataFrame({"brent": 70.0, "inr_usd": 80.0}, index=idx)
    q = pd.date_range("2005-01-01", periods=20, freq="QS-JAN")
    fq, fm = feer.run(_flat_bop(q, -0.5, **GROSS), pit, cfg)
    d = fq.dropna(subset=["misalignment_p10"])
    assert (d["misalignment_p10"] <= d["misalignment_p50"]).all() and (d["misalignment_p50"] <= d["misalignment_p90"]).all()
    assert ((d["misalignment_p10"] < d["misalignment_pct"]) & (d["misalignment_pct"] < d["misalignment_p90"])).all()
    last = fm.dropna(subset=["fair_inr"]).iloc[-1]
    assert last["fair_inr_strong"] < last["fair_inr"] < last["fair_inr_weak"]


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
