from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from inrfv.models import reer_anchor as ra

MS = pd.offsets.MonthBegin


def test_annual_series_respects_publication_and_interpolates():
    annual = pd.Series({2020: 100.0, 2021: 110.0, 2022: 130.0})
    quarters = pd.date_range("2019-01-01", "2023-10-01", freq="QS-JAN")
    # Lag 7: 2021 is public from Jul 2022, 2022 only from Jul 2023.
    s = ra.annual_to_quarters(annual, quarters, pd.Timestamp("2023-01-01"), release_lag=7)
    assert np.isnan(s["2020-01-01"])                         # nothing before the first point (Jul 2020)
    assert s["2020-07-01"] == pytest.approx(100.0)
    assert s["2021-01-01"] == pytest.approx(105.0, abs=0.3)  # linear between Jul 2020 and Jul 2021
    assert s["2023-10-01"] == pytest.approx(110.0)           # 2022 not yet public: held flat at 2021
    later = ra.annual_to_quarters(annual, quarters, pd.Timestamp("2023-07-01"), release_lag=7)
    assert later["2022-07-01"] == pytest.approx(130.0)


def test_nfa_splice_and_backcast():
    q = pd.date_range("2005-01-01", periods=8, freq="QS-JAN")
    bop = pd.DataFrame({"current_account": 10.0,
                        "niip": [np.nan] * 5 + [-100.0, -95.0, -90.0],
                        "niip_bpm5": [np.nan, np.nan, -130.0, np.nan, -110.0, -101.0, np.nan, np.nan]}, index=q)
    niip, src = ra.nfa_quarterly(bop)
    assert niip.iloc[5] == -100.0 and src.iloc[5] == "BPM6"          # BPM6 preferred
    assert niip.iloc[4] == -110.0 and src.iloc[4] == "BPM5"
    assert niip.iloc[3] == pytest.approx(-120.0) and src.iloc[3] == "interpolated"
    assert niip.iloc[1] == pytest.approx(-140.0) and src.iloc[1] == "cumulated CA"   # -130 - CA(10)
    assert niip.iloc[0] == pytest.approx(-150.0)


def test_dols_recovers_known_coefficients(rng):
    n = 200
    x = pd.DataFrame({c: np.cumsum(rng.normal(0, 0.05, n)) for c in ra.REGRESSORS},
                     index=pd.date_range("1975-01-01", periods=n, freq="QS-JAN"))
    y = 4.6 + 0.3 * x["rel_prod"] + 0.2 * x["log_tot"] + 0.5 * x["nfa_gdp"] + rng.normal(0, 0.01, n)
    b, V, _ = ra.dols(x.assign(log_reer=y), k=1, hac_lags=4)
    assert b["rel_prod"] == pytest.approx(0.3, abs=0.03)
    assert b["log_tot"] == pytest.approx(0.2, abs=0.03)
    assert b["nfa_gdp"] == pytest.approx(0.5, abs=0.03)


def _dataset(rng, months=240):
    idx = pd.date_range("2004-01-01", periods=months, freq="MS")
    reer = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, months))), index=idx)
    panel = pd.DataFrame({"reer": reer})
    pit = pd.DataFrame({"reer": reer.shift(1), "inr_usd": 50 * np.exp(np.cumsum(rng.normal(0.002, 0.01, months)))},
                       index=idx)
    q = pd.date_range(idx[0], idx[-1], freq="QS-JAN")
    bop = pd.DataFrame({"available": q + MS(6), "current_account": rng.normal(-5e3, 2e3, len(q)),
                        "gdp_usd_mn": np.linspace(7e5, 3e6, len(q)),
                        "niip": np.linspace(-6e4, -4e5, len(q)), "niip_bpm5": np.nan}, index=q)
    years = range(2000, 2025)
    annual = {"gdp_pc_ppp_india": pd.Series({y: 3000 * 1.06 ** (y - 2000) for y in years}),
              "gdp_pc_ppp_world": pd.Series({y: 15000 * 1.02 ** (y - 2000) for y in years}),
              "tot_india": pd.Series({y: 100 + rng.normal(0, 3) for y in years})}
    return SimpleNamespace(panel=panel, pit=pit, bop=bop, annual=annual)


def test_anchor_does_not_look_ahead(rng, cfg):
    cfg["models"]["reer_anchor"]["min_quarters"] = 20
    cfg["models"]["reer_anchor"]["band_draws"] = 200
    ds = _dataset(rng)
    t = ds.pit.index[150]
    a, _ = ra.run(ds, cfg)

    ds2 = _dataset(np.random.default_rng(0))
    ds2.panel["reer"], ds2.pit, ds2.bop, ds2.annual = ds.panel["reer"].copy(), ds.pit.copy(), ds.bop.copy(), dict(ds.annual)
    ds2.panel.loc[ds2.panel.index > t, "reer"] *= 1.3              # future REER
    ds2.pit.loc[ds2.pit.index > t, "reer"] *= 1.3
    late = ds2.bop["available"] > t
    ds2.bop.loc[late, ["niip", "current_account"]] *= 3            # BoP published after t
    ds2.annual["tot_india"] = ds.annual["tot_india"].copy()
    # ToT for year Y is public 18 months after December Y: with t = Jul 2016 that is 2014 and earlier.
    ds2.annual["tot_india"].loc[2015:] *= 2
    b, _ = ra.run(ds2, cfg)
    cols = ["reer_star", "gap_log"]                                # the band uses random draws per call
    pd.testing.assert_frame_equal(a.loc[:t, cols], b.loc[:t, cols])
