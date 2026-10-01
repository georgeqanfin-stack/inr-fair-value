import numpy as np
import pandas as pd

from inrfv.models import peers


def _gaps():
    idx = pd.date_range("2016-01-01", "2026-09-01", freq="MS")
    rng = np.random.default_rng(0)
    g = pd.DataFrame({c: rng.normal(0, 3, len(idx)) for c in ["IND", "TUR", "MEX"]}, index=idx)
    g.loc["2018-08":"2019-12", "TUR"] += 40            # sell-off -> undervalued
    g.loc["2023-06":"2024-06", "MEX"] -= 20            # rally -> overvalued
    g.iloc[-1] = [10.0, 30.0, -5.0]
    return g


def test_latest_ranking_and_focus_rank(cfg):
    out = peers.run(_gaps(), cfg)
    assert list(out["latest"]) == ["TUR", "IND", "MEX"] and out["focus_rank"] == 2 and out["n"] == 3


def test_episodes_pass_and_fail():
    spec = [{"country": "TUR", "label": "x", "before": ["2016-01", "2017-12"], "after": ["2018-08", "2019-12"], "expect": "weaker"},
            {"country": "MEX", "label": "y", "before": ["2016-01", "2017-12"], "after": ["2023-06", "2024-06"], "expect": "stronger"},
            {"country": "MEX", "label": "z", "before": ["2016-01", "2017-12"], "after": ["2023-06", "2024-06"], "expect": "weaker"},
            {"country": "XXX", "label": "missing", "before": ["2016-01", "2017-12"], "after": ["2018-01", "2018-12"]}]
    out = peers.episodes(_gaps(), spec)
    assert [e["pass"] for e in out] == [True, True, False]


def test_imf_check_conventions(tmp_path):
    g = _gaps()
    ya = g.groupby(g.index.year).mean()
    rows = []
    for y in (2018, 2019, 2020):
        for c in g.columns:
            rows.append({"country": c, "analysis_year": y, "ca_gap": 0.1 * ya.loc[y, c], "elasticity": 0.2,
                         "reer_gap_index": -ya.loc[y, c], "reer_gap_level": -2 * ya.loc[y, c]})
    f = tmp_path / "imf.csv"
    pd.DataFrame(rows).to_csv(f, index=False)
    out = peers.imf_check(g, f)
    s = out["stats"]["imf_reer_index"]
    assert s["pooled_corr"] > 0.999 and s["mean_rank_corr"] > 0.99 and s["same_sign"] == 1.0
