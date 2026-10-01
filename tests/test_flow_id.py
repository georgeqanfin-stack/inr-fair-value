import numpy as np
import pandas as pd
import pytest

from inrfv.models import flow_id


def _data(rng, n=400, beta=-0.2, feedback=0.0):
    """Global shocks push FPI; FPI moves INR with ``beta``; INR can feed back into FPI."""
    idx = pd.date_range("1990-01-01", periods=n, freq="MS")
    vix, us10y, dxy = rng.normal(0, 3, n), rng.normal(0, 0.2, n), rng.normal(0, 1, n)
    push = -0.4 * vix - 4 * us10y + rng.normal(0, 2, n)
    e_inr = rng.normal(0, 1, n)
    # Simultaneous system: fpi = push + feedback*inr ; inr = beta*fpi + 0.4*dxy + e
    fpi = (push + feedback * (0.4 * dxy + e_inr)) / (1 - feedback * beta)
    inr = beta * fpi + 0.4 * dxy + e_inr
    return pd.DataFrame({"inr": inr, "fpi": fpi, "fdi": rng.normal(2, 1, n), "dxy": dxy,
                         "brent": rng.normal(0, 6, n), "vix": vix, "us10y": us10y}, index=idx)


def test_iv_recovers_the_causal_effect_under_feedback(rng):
    x = _data(rng, feedback=-1.5)
    ols = np.polyfit(x["fpi"], x["inr"], 1)[0]
    iv = flow_id.two_sls(x, ["vix", "us10y"], ["dxy", "brent", "fdi"], 2)
    assert iv["first_stage_F"] > 10
    assert iv["beta"] == pytest.approx(-0.2, abs=0.06)
    assert abs(ols - -0.2) > abs(iv["beta"] - -0.2)                # OLS is biased by the feedback


def test_ordering_a_impact_matches_the_true_effect_without_feedback(rng):
    x = _data(rng, feedback=0.0)
    shock = flow_id.fpi_shock(x, flow_id.GLOBAL, 2)
    lp = flow_id.local_projection(x, shock, 2, 2, flow_id.GLOBAL + ["brent"])
    assert lp[0]["beta"] == pytest.approx(-0.2, abs=0.05)
    assert [r["h"] for r in lp] == [0, 1, 2]
