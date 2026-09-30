"""Changing data after month t must not change any model output at or before t."""

import numpy as np
import pandas as pd
import pytest

from inrfv import backtest
from inrfv.models import beer, composite, feer, structural


def _perturb_after(df, t, cols, factor=1.3):
    out = df.copy()
    out.loc[out.index > t, cols] = out.loc[out.index > t, cols] * factor
    return out


@pytest.fixture
def pit(months, rng):
    n = len(months)
    p = pd.DataFrame(index=months)
    p["inr_usd"] = 45 * np.exp(np.cumsum(rng.normal(0.003, 0.015, n)))
    p["reer"] = 100 + np.cumsum(rng.normal(0, 1, n))
    p["dxy"] = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    p["brent"] = 60 * np.exp(np.cumsum(rng.normal(0, 0.05, n)))
    p["vix"] = 20 + rng.normal(0, 3, n)
    p["real_rate_diff"] = rng.normal(1, 1, n)
    p["fpi_pct_gdp"] = rng.normal(0, 1, n)
    p["log_inr"] = np.log(p["inr_usd"])
    p["log_dxy"] = np.log(p["dxy"])
    p["log_brent"] = np.log(p["brent"])
    return p


def test_structural_one_sided_hp(pit, cfg):
    t = pit.index[150]
    a = structural.run(pit, cfg)
    b = structural.run(_perturb_after(pit, t, ["reer", "inr_usd"]), cfg)
    pd.testing.assert_series_equal(a.loc[:t, "gap_log"], b.loc[:t, "gap_log"])
    # ...whereas the two-sided (ex-post) trend does move: that is the leak we removed.
    assert not np.allclose(a.loc[:t, "reer_trend_expost"], b.loc[:t, "reer_trend_expost"])


def test_beer_expanding_window(pit, cfg):
    t = pit.index[150]
    cols = ["log_inr", "inr_usd", "log_dxy", "vix"]
    a, _ = beer.run(pit, cfg)
    b, _ = beer.run(_perturb_after(pit, t, cols), cfg)
    pd.testing.assert_series_equal(a.loc[:t, "fair_inr"], b.loc[:t, "fair_inr"])


def _bop(pit, rng):
    q = pd.date_range(pit.index[0], pit.index[-1], freq="QS-JAN")
    bop = pd.DataFrame(index=q)
    bop["available"] = q + pd.offsets.MonthBegin(6)
    bop["current_account_pct_gdp"] = rng.normal(-1.5, 1, len(q))
    bop["brent_q"] = pit["brent"].reindex(q).to_numpy()
    bop["inr_q"] = pit["inr_usd"].reindex(q).to_numpy()
    bop["fdi_bop"], bop["loans"], bop["gdp_usd_mn"] = 5000.0, 3000.0, 3e6
    return bop


def test_feer_uses_released_quarters_only(pit, cfg, rng):
    bop = _bop(pit, rng)
    t = pit.index[150]
    _, m_a = feer.run(bop, pit, cfg)
    bop2 = bop.copy()
    late = bop2["available"] > t
    bop2.loc[late, "current_account_pct_gdp"] += 5
    bop2.loc[late, "brent_q"] *= 2
    _, m_b = feer.run(bop2, _perturb_after(pit, t, ["brent"], 2.0), cfg)
    pd.testing.assert_series_equal(m_a.loc[:t, "gap_log"], m_b.loc[:t, "gap_log"])


def test_backtest_forecast_ignores_future_prices(pit, cfg):
    comp = pd.DataFrame({"log_inr": pit["log_inr"],
                         "ect": np.sin(np.arange(len(pit)) / 7.0) * 0.05}, index=pit.index)
    t = pit.index[180]
    a = backtest.forecasts(comp, 12, 60)
    b = backtest.forecasts(_perturb_after(comp, t, ["log_inr"], 1.1), 12, 60)
    cols = ["f_drift", "f_ecm", "alpha"]
    pd.testing.assert_frame_equal(a.loc[:t, cols], b.loc[:t, cols])


def test_backtest_training_targets_fully_realised(pit):
    comp = pd.DataFrame({"log_inr": pit["log_inr"], "ect": 0.01}, index=pit.index)
    h = 12
    fc = backtest.forecasts(comp, h, 60)
    first = fc.index[0]
    # First forecast needs 60 realised targets, the last of which ends at the origin.
    assert pit.index.get_loc(first) == 60 - 1 + h
    assert (fc["n_train"].diff().dropna() == 1).all()


def test_composite_requires_both_components(pit, cfg):
    reer = pd.DataFrame({"gap_log": 0.1}, index=pit.index)
    fm = pd.DataFrame({"gap_log": np.where(pit.index < pit.index[50], np.nan, -0.1)}, index=pit.index)
    comp = composite.run(pit, reer, fm, cfg)
    assert comp["ect"].iloc[:50].isna().all()
    assert comp["ect"].iloc[60] == pytest.approx(0.0)
