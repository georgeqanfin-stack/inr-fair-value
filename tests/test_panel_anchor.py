from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from inrfv.data.panel import PanelData
from inrfv.models import panel_anchor as pa

COUNTRIES = ["IND", "AAA", "BBB", "CCC", "DDD", "EEE"]


def _pdata(rng, years=range(1994, 2026), beta=0.3, stationary=True):
    """Synthetic panel: log REER = a_c + beta * rel_prod + noise (stationary or random walk)."""
    months = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    gdp, reer = {}, {}
    wld = pd.Series({y: 10000 * 1.02 ** (y - years[0]) for y in years})
    for i, c in enumerate(COUNTRIES):
        growth = 1.02 + 0.01 * i
        g = pd.Series({y: 2000 * (1 + i) * growth ** (y - years[0]) for y in years})
        gdp[c] = g
        rp = np.log(g / wld)
        noise = rng.normal(0, 0.03, len(years))
        e = noise if stationary else np.cumsum(noise)
        annual = 4.6 + 0.1 * i + beta * rp.to_numpy() + e
        reer[c] = pd.Series(np.exp(np.repeat(annual, 12)), index=months)
    gdp["WLD"] = wld
    wdi = {"gdp_pc_ppp": pd.DataFrame(gdp),
           "tot": pd.DataFrame({c: 100.0 for c in COUNTRIES + ["WLD"]}, index=list(years)),
           "gov_cons": pd.DataFrame({c: 12.0 for c in COUNTRIES + ["WLD"]}, index=list(years)),
           "openness": pd.DataFrame({c: 40.0 for c in COUNTRIES + ["WLD"]}, index=list(years))}
    return PanelData(reer=pd.DataFrame(reer), wdi=wdi, countries=COUNTRIES)


def test_annual_panel_respects_publication(rng, cfg):
    p = cfg["models"]["panel_anchor"]
    pdata = _pdata(rng)
    panel = pa.annual_panel(pdata, p, pd.Timestamp("2020-06-01"))
    years = panel.loc["IND"]
    # REER for 2019 is complete and public (Dec 2019 + 1 month); 2020 is not.
    assert years["log_reer"].dropna().index.max() == 2019
    # WDI 2019 is public only from Jul 2020 (lag 7): latest productivity year is 2018.
    assert years["rel_prod"].dropna().index.max() == 2018


def test_estimate_recovers_pooled_coefficient_and_country_effects(rng, cfg):
    p = cfg["models"]["panel_anchor"]
    pdata = _pdata(rng, beta=0.3)
    panel = pa.annual_panel(pdata, p, pd.Timestamp("2026-12-01"))
    fit = pa.estimate(panel, ["rel_prod"], k=1)
    assert fit["b"]["rel_prod"] == pytest.approx(0.3, abs=0.05)
    assert fit["n_countries"] == len(COUNTRIES)
    # Country effects keep their ordering (a_c rises by 0.1 per country by construction).
    assert fit["alpha"]["CCC"] > fit["alpha"]["AAA"]


def test_panel_cointegration_distinguishes_stationary_from_random_walk(cfg):
    p = cfg["models"]["panel_anchor"]
    ts = pd.Timestamp("2026-12-01")
    good = pa.estimate(pa.annual_panel(_pdata(np.random.default_rng(1)), p, ts), ["rel_prod"], 1)
    bad = pa.estimate(pa.annual_panel(_pdata(np.random.default_rng(2), stationary=False), p, ts), ["rel_prod"], 1)
    assert pa.panel_cointegration(good["resid"], 1)["cointegrated_5pct"]
    assert not pa.panel_cointegration(bad["resid"], 1)["cointegrated_5pct"]


def test_panel_anchor_does_not_look_ahead(rng, cfg):
    cfg["models"]["panel_anchor"]["band_draws"] = 100
    cfg["models"]["panel_anchor"]["central_spec"] = "prod"
    pdata = _pdata(rng)
    idx = pd.date_range("2004-01-01", "2025-12-01", freq="MS")
    ds = SimpleNamespace(pit=pd.DataFrame({"inr_usd": 50.0}, index=idx))
    t = pd.Timestamp("2016-03-01")
    a, _ = pa.run(ds, pdata, cfg)

    reer2 = pdata.reer.copy()
    reer2.loc[reer2.index >= "2016-03-01"] *= 1.5                    # Mar 2016 onward is public only after t
    gdp2 = pdata.wdi["gdp_pc_ppp"].copy()
    gdp2.loc[2015:] *= 2                                               # 2015 WDI is public only from Jul 2016
    pdata2 = PanelData(reer=reer2, wdi={**pdata.wdi, "gdp_pc_ppp": gdp2}, countries=pdata.countries)
    b, _ = pa.run(ds, pdata2, cfg)
    cols = ["reer_bis", "reer_star", "gap_log"]
    pd.testing.assert_frame_equal(a.loc[:t, cols], b.loc[:t, cols])
    assert not np.allclose(a.loc["2016-08-01":, "reer_star"], b.loc["2016-08-01":, "reer_star"])
