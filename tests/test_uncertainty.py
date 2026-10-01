import numpy as np
import pandas as pd
import pytest

from inrfv.models import panel_anchor, uncertainty


def test_bootstrap_fit_recovers_slope_and_spread(rng):
    years = list(range(1995, 2025))
    rows = []
    for i, c in enumerate(["IND", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]):
        rp = np.cumsum(rng.normal(0.02, 0.01, len(years))) + i * 0.1
        lr = 4.6 + 0.1 * i + 0.3 * rp + rng.normal(0, 0.03, len(years))
        rows += [{"country": c, "year": y, "log_reer": a, "rel_prod": b} for y, a, b in zip(years, lr, rp)]
    panel = pd.DataFrame(rows).set_index(["country", "year"])
    b, a = panel_anchor.bootstrap_fit(panel, ["rel_prod"], 1, 300, np.random.default_rng(1))
    assert b.shape == (300, 1) and a.shape == (300,)
    assert np.median(b[:, 0]) == pytest.approx(0.3, abs=0.08)
    assert np.std(b[:, 0]) > 0


def test_feer_draws_centre_on_the_central_estimate(cfg):
    q = pd.DataFrame({"norm_central": [-2.0], "norm_central_se": [0.7], "exports_pct_gdp": [20.0],
                      "imports_pct_gdp": [24.0], "semi_elasticity": [-0.152], "cad_underlying": [-1.0]})
    u = {"ca_measurement_sd": 0.2}
    d = uncertainty.feer_draws(q, cfg["models"]["feer"], u, 20000, np.random.default_rng(2))
    central = np.log1p(-(-1.0 - -2.0) / -0.152 / 100)
    assert np.median(d[0]) == pytest.approx(central, abs=0.01)


def test_coverage_counts_inside_below_above():
    idx = pd.date_range("2020-01-01", periods=4, freq="MS")
    ex = pd.DataFrame({"ect_ex": [0.0, 0.1, 0.3, -0.2]}, index=idx)
    lo, hi = pd.Series(-0.1, idx), pd.Series(0.2, idx)
    c = uncertainty.coverage(ex, {"b": (lo, hi)})["b"]
    assert c["n"] == 4 and c["coverage"] == 0.5 and c["above"] == 0.25 and c["below"] == 0.25


def test_apply_corridor_keeps_end_to_end():
    idx = pd.date_range("2020-01-01", periods=3, freq="MS")
    comp = pd.DataFrame({"inr_usd": 80.0, "ect_lo": -0.1, "ect_hi": 0.3, "fair_inr_strong": 1.0, "fair_inr_weak": 1.0}, idx)
    series = pd.DataFrame({"lo": [np.nan, 0.0, 0.05], "hi": [np.nan, 0.2, 0.25]}, idx)
    uncertainty.apply_corridor(comp, series)
    assert comp["ect_lo"].tolist() == [-0.1, 0.0, 0.05] and comp["ect_lo_e2e"].tolist() == [-0.1] * 3
    assert comp["fair_inr_strong"].iloc[1] == pytest.approx(80 * np.exp(-0.2))
    assert comp.attrs["corridor"] == "joint bootstrap"


def test_conformal_k_is_the_finite_sample_quantile():
    s = np.arange(1, 10, dtype=float)                   # n = 9: ceil(10 * 0.8) = 8th smallest
    assert uncertainty.conformal_k(s, 0.8) == 8.0
    assert uncertainty.conformal_k(np.array([0.5]), 0.8) == 0.5


def test_recalibration_widens_a_too_narrow_corridor_and_respects_publication():
    idx = pd.date_range("2015-01-01", "2024-12-01", freq="MS")
    rng = np.random.default_rng(4)
    years = idx.year.to_numpy()
    x = pd.Series(np.repeat(rng.normal(0, 0.04, 10), 12), idx)       # one ex-post error a year
    bands = pd.DataFrame({"lo": -0.02, "mid": 0.0, "hi": 0.02}, idx)    # far too narrow
    ex = pd.DataFrame({"ect_ex": x})
    published = {int(y): pd.Timestamp(int(y) + 1, 7, 1) for y in set(years)}
    rc = {"nominal": 0.8, "min_years": 3, "methods": ["scale", "shift_scale"], "prefer_gap": 0.05}
    out = uncertainty.recalibrate(bands, ex, published, rc)
    assert out["loyo"]["raw"]["coverage"] < 0.5
    assert out["loyo"]["scale"]["coverage"] > out["loyo"]["raw"]["coverage"]
    assert out["choice"] in ("scale", "shift_scale") and out["params"]["scale"]["k"] > 1
    assert out["realtime_from"] == "2018-07"                          # 2015-17 published by Jul 2018
    s = out["series"]
    assert s.loc[:"2018-06"].isna().all().all() and s.loc["2018-07":].notna().all().all()


def test_recalibration_keeps_a_well_calibrated_corridor():
    idx = pd.date_range("2015-01-01", "2024-12-01", freq="MS")
    x = pd.Series(np.repeat(np.linspace(-0.009, 0.009, 10), 12), idx)  # always inside +/-0.01
    bands = pd.DataFrame({"lo": -0.0101, "mid": 0.0, "hi": 0.0101}, idx)
    out = uncertainty.recalibrate(bands, pd.DataFrame({"ect_ex": x}), {y: pd.Timestamp(y + 1, 7, 1) for y in range(2015, 2025)},
                                  {"nominal": 1.0, "min_years": 3, "methods": ["scale"], "prefer_gap": 0.05})
    assert out["choice"] == "raw"
