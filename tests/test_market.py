import numpy as np
import pandas as pd
import pytest

from inrfv.models import market


def _pit(rng, n=300, uip_slope=1.0):
    idx = pd.date_range("2000-01-01", periods=n, freq="MS")
    prem3 = 4 + np.cumsum(rng.normal(0, 0.3, n)) * 0.2
    dep = np.empty(n)                                  # monthly log depreciation, % (not annualised)
    dep[:] = rng.normal(0, 1.5, n)
    lr = np.log(50) + np.cumsum(dep) / 100
    # make realised 3-month depreciation track the premium: add premium/12 per month
    lr = lr + np.cumsum(uip_slope * np.r_[0, prem3[:-1]] / 1200)
    pit = pd.DataFrame({"inr_usd": np.exp(lr), "fwd_premium_3m": prem3, "fwd_premium_6m": prem3 + 0.1,
                        "dxy": 100 * np.exp(np.cumsum(rng.normal(0, 1, n)) / 100),
                        "india_policy_rate": 6.0, "fed_funds_rate": 3.0}, index=idx)
    pit["fwd_spread"] = pit["fwd_premium_3m"] - (pit["india_policy_rate"] - pit["fed_funds_rate"])
    return pit


def test_forward_rates_and_month_labels(rng, cfg):
    pit = _pit(rng)
    panel = pit.copy()
    panel.iloc[-2:, panel.columns.get_loc("fwd_premium_3m")] = np.nan    # last two months not yet observed
    panel.iloc[-2:, panel.columns.get_loc("fwd_premium_6m")] = np.nan
    out = market.run(pit, panel, cfg)
    f3 = out["forwards"]["3m"]
    assert f3["month"] == panel.index[-3].strftime("%Y-%m")
    assert f3["forward"] == pytest.approx(pit["inr_usd"].iloc[-1] * (1 + panel["fwd_premium_3m"].iloc[-3] * 3 / 1200))
    assert out["spread"]["month"] == f3["month"]


def test_uip_slope_is_recovered(rng, cfg):
    u = market.uip(_pit(rng, n=600), 3, "fwd_premium_3m", 6)
    assert u["slope"] == pytest.approx(1.0, abs=0.6)
    assert u["nobs"] == 597


def test_no_premia_means_no_block(rng, cfg):
    pit = _pit(rng).drop(columns=["fwd_premium_3m"])
    assert market.run(pit, pit, cfg) is None
