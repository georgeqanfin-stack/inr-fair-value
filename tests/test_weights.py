import numpy as np
import pandas as pd
import pytest

from inrfv.models import weights


def _inputs(rng, n=240):
    idx = pd.date_range("2005-01-01", periods=n, freq="MS")
    gr = pd.Series(np.cumsum(rng.normal(0, 0.01, n)) * 0.3, idx)
    gf = pd.Series(np.cumsum(rng.normal(0, 0.01, n)) * 0.3, idx)
    log_inr = pd.Series(np.cumsum(rng.normal(0.003, 0.02, n)), idx)
    comp = pd.DataFrame({"log_inr": log_inr, "gap_reer": gr, "gap_feer": gf, "ect": (gr + gf) / 2})
    reer = pd.DataFrame({"gap_log_lo": gr - 0.10, "gap_log_hi": gr + 0.10}, index=idx)     # wide band
    feer = pd.DataFrame({"gap_log_lo": gf - 0.05, "gap_log_hi": gf + 0.05}, index=idx)     # half as wide
    return comp, reer, feer


def test_inverse_variance_weights_follow_band_widths(rng):
    comp, reer, feer = _inputs(rng)
    w = weights.inverse_variance(reer, feer)
    assert w.iloc[-1] == pytest.approx(0.2)            # variance ratio 4:1 -> REER weight 1/5


def test_performance_weights_use_only_realised_errors(rng, cfg):
    comp, reer, feer = _inputs(rng)
    w = weights.performance(comp, 12, 60, min_errors=24)
    first = w[w != 0.5].first_valid_index()
    # first forecast at month 71 (60 realised 12-month targets: months 0-59 -> forecast at 59 + 12);
    # its error is known 12 months later and 24 errors are needed: first move at 71 + 12 + 23 = 106
    assert first is not None and comp.index.get_loc(first) == 71 + 12 + 23


def test_rule_keeps_equal_unless_clearly_better(rng, cfg):
    comp, reer, feer = _inputs(rng)
    out = weights.run(comp, reer, feer, cfg)
    h = cfg["backtest"]["headline_horizon"]
    eq = out["schemes"]["equal"]["by_horizon"][h]
    if out["rule_choice"] != "equal":
        ch = out["schemes"][out["rule_choice"]]["by_horizon"][h]
        assert eq["rmse_ratio"] - ch["rmse_ratio"] >= 0.01 and ch["cw_p"] < eq["cw_p"]
    assert set(out["schemes"]) >= {"equal", "inverse_variance", "performance", "reer_only", "feer_only"}
    assert out["headline_range"][0] <= out["schemes"]["equal"]["misalignment_last"] <= out["headline_range"][1]
