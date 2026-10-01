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
