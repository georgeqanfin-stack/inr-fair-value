from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from inrfv.models import beer


def synthetic_ds(rng, n=300, b_dxy=0.7, b_prod=-0.4, noise=0.01):
    """Real INR/USD cointegrated with DXY and productivity; PPP holds in the long run."""
    idx = pd.date_range("2000-01-01", periods=n, freq="MS")
    log_dxy = 4.6 + np.cumsum(rng.normal(0, 0.01, n))
    years = range(1998, 2000 + n // 12 + 2)
    ind = pd.Series({y: 2000 * 1.06 ** (y - 1998) for y in years})
    usa = pd.Series({y: 50000 * 1.015 ** (y - 1998) for y in years})
    cpi_in = 100 * np.exp(np.cumsum(np.full(n, 0.005)))
    cpi_us = 100 * np.exp(np.cumsum(np.full(n, 0.002)))
    panel = pd.DataFrame({"cpi_india": cpi_in, "cpi_us": cpi_us}, index=idx)
    ds = SimpleNamespace(panel=panel, annual={"gdp_pc_ppp_india": ind, "gdp_pc_ppp_usa": usa})
    ds.pit = pd.DataFrame({"log_dxy": log_dxy, "log_brent": np.log(70.0) + np.cumsum(rng.normal(0, 0.05, n)),
                           "real_rate_diff": rng.normal(1, 0.5, n)},
                          index=idx)
    # Build q from the same point-in-time inputs the model sees, then the nominal rate.
    tmp = beer.build_inputs(SimpleNamespace(panel=panel, annual=ds.annual,
                                            pit=ds.pit.assign(log_inr=0.0)), _cfg())
    q = 1.0 + b_dxy * log_dxy + b_prod * tmp["rel_prod"].to_numpy() + rng.normal(0, noise, n)
    ds.pit["log_inr"] = q + tmp["rel_price"].bfill().to_numpy()
    ds.pit["inr_usd"] = np.exp(ds.pit["log_inr"])
    return ds


def _cfg():
    from inrfv.config import load_config
    return load_config()


def test_beer_recovers_coefficients_with_ppp_imposed(cfg):
    ds = synthetic_ds(np.random.default_rng(1))
    cfg["models"]["beer"]["specs"]["test"] = ["log_dxy", "rel_prod"]
    cfg["models"]["beer"]["central_spec"] = "test"
    out, diag = beer.run(ds, cfg)
    c = diag["specs"]["test"]["coef"]
    assert c["log_dxy"] == pytest.approx(0.7, abs=0.05)
    assert c["rel_prod"] == pytest.approx(-0.4, abs=0.1)
    assert diag["specs"]["test"]["engle_granger"]["cointegrated_5pct"]
    # With a well-specified model the gap is small and centred on zero.
    g = out["misalignment_pct"].dropna()
    assert abs(g.mean()) < 2 and g.abs().max() < 10


def test_beer_is_invariant_to_the_cpi_base(cfg):
    # Rescaling a CPI index (a change of base year) must not move the fair value:
    # the constant absorbs it. This is what makes CPI base changes harmless.
    ds = synthetic_ds(np.random.default_rng(2))
    a, _ = beer.run(ds, cfg)
    ds.panel["cpi_india"] *= 1.10
    ds.panel["cpi_us"] *= 0.8
    b, _ = beer.run(ds, cfg)
    pd.testing.assert_series_equal(a["fair_inr"], b["fair_inr"], rtol=1e-6)


def test_band_brackets_current_beer(cfg):
    out, _ = beer.run(synthetic_ds(np.random.default_rng(4)), cfg)
    d = out.dropna(subset=["gap_log"])
    assert (d["gap_log_lo"] <= d["gap_log"]).all() and (d["gap_log"] <= d["gap_log_hi"]).all()
