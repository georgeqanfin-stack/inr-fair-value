import numpy as np
import pandas as pd
import pytest

from inrfv.models import benchmark


def _csv(tmp_path):
    f = tmp_path / "imf.csv"
    pd.DataFrame({"analysis_year": [2023, 2024], "published": ["2024-07", "2025-07"], "ca_actual": [-0.8, -0.8],
                  "ca_cyc_adj": [-0.5, -0.6], "ca_norm": [-2.2, -2.0], "ca_gap": [1.8, 1.4],
                  "reer_gap_index": [5.9, 5.4], "reer_gap_level": [5.2, -4.1], "elasticity": [0.18, 0.2],
                  "source": "x"}).to_csv(f, index=False)
    return f


def test_load_puts_imf_on_our_sign_convention(tmp_path):
    d = benchmark.load(_csv(tmp_path))
    assert d["imf_ca"].tolist() == pytest.approx([10.0, 7.0])          # CA gap / elasticity, + = undervalued
    assert d["imf_reer_level"].tolist() == [-5.2, 4.1]                   # IMF + = overvalued, flipped


def test_ours_table_year_average_and_reading_at_publication(tmp_path):
    d = benchmark.load(_csv(tmp_path))
    idx = pd.date_range("2023-01-01", "2025-12-01", freq="MS")
    s = pd.Series(np.arange(len(idx), dtype=float), idx)
    t = benchmark.ours_table(d, {"composite": s})
    assert t.loc[0, "composite_year"] == pytest.approx(5.5)              # mean of Jan-Dec 2023 = 0..11
    assert t.loc[0, "composite_at_pub"] == 18.0                          # Jul 2024 is the 19th month
    assert t.loc[1, "composite_at_pub"] == 30.0


def test_agreement_statistics():
    a = pd.Series([1.0, 2.0, 3.0, -1.0])
    b = pd.Series([2.0, 3.0, 5.0, 1.0])
    out = benchmark.agreement(a, b)
    assert out["n"] == 4 and out["same_sign"] == 0.75
    assert out["mean_diff_pp"] == pytest.approx(-1.5)
    assert benchmark.agreement(a.iloc[:2], b.iloc[:2]) == {"n": 2}
