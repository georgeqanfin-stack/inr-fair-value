import numpy as np
import pandas as pd
import pytest

from inrfv.stats import panel_coint as pc


def _panel(rng, coint, n=10, T=30):
    rows = []
    for i in range(n):
        x = np.cumsum(rng.normal(0.02, 0.03, T))
        if coint:
            u = np.zeros(T)
            for t in range(1, T):
                u[t] = 0.3 * u[t - 1] + rng.normal(0, 0.05)
            y = 0.3 * x + u
        else:
            y = np.cumsum(rng.normal(0, 0.05, T))
        rows += [{"country": f"C{i}", "year": 1990 + t, "log_reer": y[t], "rel_prod": x[t]} for t in range(T)]
    return pd.DataFrame(rows).set_index(["country", "year"])


def test_holm_and_bh_known_values():
    p = {"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.20}
    assert pc.holm(p) == pytest.approx({"a": 0.04, "c": 0.09, "b": 0.09, "d": 0.20})
    assert pc.bh(p) == pytest.approx({"a": 0.04, "c": 0.0533333, "b": 0.0533333, "d": 0.20})


def test_family_contains_every_subset_with_the_required_variable():
    f = pc.family(["rel_prod", "a", "b", "c", "d"], "rel_prod")
    assert len(f) == 16 and all(v[0] == "rel_prod" for v in f.values())
    assert len({frozenset(v) for v in f.values()}) == 16


def test_statistics_are_more_negative_under_cointegration(rng):
    s_c = pc.statistics(pc.balanced(_panel(rng, True), ["rel_prod"]))
    s_n = pc.statistics(pc.balanced(_panel(rng, False), ["rel_prod"]))
    for k in ("group_adf", "panel_adf", "Gt", "Pt"):
        assert s_c[k] < s_n[k]


def test_bootstrap_p_values_separate_the_cases():
    c = pc.test(_panel(np.random.default_rng(3), True), ["rel_prod"], 49, 1)
    n = pc.test(_panel(np.random.default_rng(4), False), ["rel_prod"], 49, 1)
    assert c["testable"] and c["p"]["group_adf"] < 0.05 and n["p"]["group_adf"] > 0.05


def test_too_few_years_is_not_testable(rng):
    short = _panel(rng, True, T=8)
    assert pc.test(short, ["rel_prod"], 9, 1)["testable"] is False
