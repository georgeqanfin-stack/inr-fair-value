import pandas as pd
import pytest
from conftest import ROOT

from inrfv import vintages
from inrfv.data import alfred, dbie


def test_merge_older_prefers_the_earlier_vintage():
    idx = pd.date_range("2025-01-01", periods=4, freq="MS")
    api = pd.Series([1.0, 2.0, 3.1, 4.0], idx)                 # later release: revised Mar, adds Apr
    xlsx = pd.Series([1.0, 2.0, 3.0], idx[:3])
    assert dbie.merge(api, xlsx).tolist() == [1.0, 2.0, 3.1, 4.0]
    assert dbie.merge_older(api, xlsx).tolist() == [1.0, 2.0, 3.0, 4.0]


def test_compare_measures_point_in_time_differences():
    idx = pd.date_range("2025-01-01", periods=5, freq="MS")
    cur = pd.DataFrame({"misalignment_pct": [5, 6, 7, 8, 9.0], "gap_reer": 0.1, "gap_feer": [0.05] * 5}, idx)
    early = cur.copy()
    early.loc[idx[3], "misalignment_pct"] = 8.5
    early.loc[idx[3], "gap_feer"] = 0.045
    out = vintages.compare(cur, early, until=idx[3])
    assert out["n_months"] == 4 and out["n_changed"] == 1
    assert out["max_abs_pp"] == pytest.approx(0.5) and out["max_month"] == "2025-04"
    assert out["by_component_mean_abs_pp"]["reer"] == 0
    assert out["last"]["diff"] == pytest.approx(-0.5)


def test_materialize_and_vintage_config(tmp_path, cfg):
    raw = vintages.materialize("HEAD", ROOT, tmp_path)
    assert (raw / "MANIFEST.sha256").exists() and (raw / "manual").is_dir()
    v = vintages.vintage_config(cfg, raw)
    assert v["paths"]["raw"] == str(raw)
    assert v["paths"]["dbie_cache"] == str(raw / "dbie") and v["paths"]["manual"] == str(raw / "manual")
    assert cfg["paths"]["raw"] == "data/raw"                    # original config untouched


def _releases():
    # Jan-2024 CPI first published 100, revised to 101 in Mar 2025; Jan-2025 published 103 on 12 Feb 2025.
    rows = [("2024-01-01", "2024-02-13", 100.0), ("2024-01-01", "2025-03-01", 101.0),
            ("2025-01-01", "2025-02-12", 103.0), ("2024-12-01", "2025-01-15", 102.0)]
    return pd.DataFrame(rows, columns=["date", "realtime_start", "value"]).astype(
        {"date": "datetime64[ns]", "realtime_start": "datetime64[ns]"})


def test_alfred_uses_the_vintage_public_at_each_month_end():
    rel = _releases()
    idx = pd.DatetimeIndex(["2025-01-01", "2025-02-01", "2025-03-01"])
    yoy = alfred.yoy_as_known(rel, idx)
    assert pd.isna(yoy.iloc[0])                                 # Jan 2025 CPI not out by end-Jan; Dec has no base
    assert yoy.iloc[1] == pytest.approx(3.0)                    # end-Feb: 103 / 100 (first release)
    assert yoy.iloc[2] == pytest.approx((103 / 101 - 1) * 100)  # end-Mar: base revised to 101
    assert alfred.first_release(rel).loc["2024-01-01"] == 100.0


def test_alfred_without_key_or_cache_returns_none(tmp_path):
    assert alfred.fetch_releases("CPIAUCSL", tmp_path, api_key=None) is None
