import numpy as np
import pandas as pd
import pytest

from inrfv.data.build import GdpNowcaster, build_pit, flat_runs, splice_cpi_india
from inrfv.data.fred import ratio_splice, to_monthly


def test_ratio_splice_removes_level_break():
    idx = pd.date_range("2004-01-01", periods=48, freq="MS")
    major = pd.Series(np.linspace(80, 90, 48), index=idx)
    broad = (major * 1.19)[idx >= "2006-01-01"]
    spliced, ratio = ratio_splice(broad, major, 12)
    assert ratio == pytest.approx(1.19)
    jump = np.log(spliced["2006-01-01"] / spliced["2005-12-01"])
    assert abs(jump) < 0.01
    assert spliced.index.min() == idx.min()


def test_ratio_splice_requires_overlap():
    a = pd.Series([1.0, 2.0], index=pd.date_range("2006-01-01", periods=2, freq="MS"))
    b = pd.Series([1.0, 2.0], index=pd.date_range("2000-01-01", periods=2, freq="MS"))
    with pytest.raises(ValueError):
        ratio_splice(a, b)


def test_cpi_splice_single_method():
    idx = pd.date_range("2024-01-01", periods=15, freq="MS")
    oecd = pd.Series(np.linspace(150, 157, 15), index=idx)
    mospi = pd.Series(np.linspace(100, 104, 16), index=pd.date_range("2025-01-01", periods=16, freq="MS"))
    oecd = oecd[oecd.index <= "2025-03-01"]
    out, meta = splice_cpi_india(oecd, mospi)
    assert meta["overlap"] == ["2025-01", "2025-02", "2025-03"]
    assert out.index.max() == mospi.index.max()
    assert out.loc["2025-04-01"] == pytest.approx(mospi.loc["2025-04-01"] * meta["ratio"])


def test_flat_runs_detects_placeholders():
    s = pd.Series([1, 2, 3, 3, 3, 4], index=pd.date_range("2025-01-01", periods=6, freq="MS"), dtype=float)
    assert flat_runs(s) == [("2025-03", "2025-05", 3.0)]


def test_to_monthly_mean_and_last():
    d = pd.Series([1.0, 3.0, 10.0], index=pd.to_datetime(["2020-01-02", "2020-01-30", "2020-02-03"]))
    assert to_monthly(d, "mean").tolist() == [2.0, 10.0]
    assert to_monthly(d, "last").tolist() == [3.0, 10.0]


def test_gdp_nowcaster_respects_release_lag():
    gdp = pd.Series({2021: 100.0, 2022: 110.0, 2023: 121.0})
    nc = GdpNowcaster(gdp, release_lag_months=7, lookback=3)
    # 2023 GDP is public from end-July 2024, not before.
    assert list(nc.available_years(pd.Timestamp("2024-06-01")).index) == [2021, 2022]
    assert list(nc.available_years(pd.Timestamp("2024-07-01")).index) == [2021, 2022, 2023]
    # One year after the mid-point of the last known year grows by the average rate (10%).
    assert nc.inr(pd.Timestamp("2024-07-01"), pd.Timestamp("2024-07-01")) == pytest.approx(133.1)


def _toy_panel(n=40):
    idx = pd.date_range("2020-01-01", periods=n, freq="MS")
    p = pd.DataFrame(index=idx)
    for c in ["inr_usd", "reer", "neer", "fx_reserves_usd_mn", "dxy", "vix", "brent", "us_10y_yield",
              "fed_balance_sheet", "fed_funds_rate", "india_policy_rate", "cpi_us", "cpi_india",
              "exports_usd_mn", "imports_usd_mn", "fpi_usd_mn"]:
        p[c] = np.arange(1, n + 1, dtype=float) + 50
    return p


def test_build_pit_applies_publication_lags(cfg):
    panel = _toy_panel()
    lag = cfg["publication_lag"]
    nc = GdpNowcaster(pd.Series({2017: 1e12, 2018: 1.1e12, 2019: 1.2e12}), 7, 3)
    pit = build_pit(panel, lag, nc)
    t = pd.Timestamp("2022-06-01")
    assert pit.loc[t, "inr_usd"] == panel.loc[t, "inr_usd"]                       # lag 0
    assert pit.loc[t, "reer"] == panel.shift(lag["reer"]).loc[t, "reer"]         # lag 1
    assert pit.loc[t, "fpi_usd_mn"] == panel.shift(lag["fpi_usd_mn"]).loc[t, "fpi_usd_mn"]
    # YoY CPI at t refers to month t - lag.
    ref = t - pd.offsets.MonthBegin(lag["cpi_india"])
    expected = (panel.loc[ref, "cpi_india"] / panel.loc[ref - pd.offsets.MonthBegin(12), "cpi_india"] - 1) * 100
    assert pit.loc[t, "cpi_india_yoy"] == pytest.approx(expected)


def test_fill_inside_never_extends():
    from inrfv.data.build import fill_inside
    idx = pd.date_range("2026-01-01", periods=6, freq="MS")
    m = pd.Series([1.0, 2.0, None, 4.0, None, None], idx)            # gap in Mar; ends Apr
    other = pd.Series([9.0] * 6, idx)
    out, filled = fill_inside(m, other)
    assert filled == ["2026-03"] and out.loc["2026-03-01"] == 9.0
    assert out.loc["2026-05-01":].isna().all()


def test_cpi_2024_api_preferred_manual_checks(tmp_path):
    from inrfv.data.build import cpi_2024_series
    f = tmp_path / "m.csv"
    pd.DataFrame({"date": ["2026-07-01", "2026-08-01"], "cpi": [107.95, 108.80]}).to_csv(f, index=False)
    api = pd.DataFrame({"index": [107.95], "inflation": [4.45], "provisional": [False]},
                       index=pd.DatetimeIndex(["2026-07-01"], name="date"))
    warnings, meta = [], {}
    s = cpi_2024_series(api, f, warnings, meta)
    assert s.loc["2026-08-01"] == 108.80 and not warnings                # manual fills the month the API lacks
    api.loc["2026-07-01", "index"] = 108.5
    cpi_2024_series(api, f, warnings, meta)
    assert warnings and "differ" in warnings[0]
