import numpy as np
import pandas as pd
import pytest

from inrfv.models import flows


def _panel(rng, n=180, b_fpi=-0.15, b_dxy=0.5):
    idx = pd.date_range("2011-01-01", periods=n, freq="MS")
    fpi = rng.normal(0, 3, n)
    fdi = rng.normal(2, 2, n)
    dxy = rng.normal(0, 1.5, n)
    brent = rng.normal(0, 6, n)
    inr = 0.4 + b_fpi * fpi + b_dxy * dxy + rng.normal(0, 0.3, n)
    lvl = lambda d: 100 * np.exp(np.cumsum(d) / 100)
    return pd.DataFrame({"inr_usd": lvl(inr), "fpi_usd_mn": fpi * 1000, "fdi_usd_mn": fdi * 1000,
                         "dxy": lvl(dxy), "brent": lvl(brent)}, index=idx)


@pytest.fixture
def fcfg(cfg):
    cfg["models"]["flows"]["start"] = None
    return cfg


def test_recovers_coefficients(rng, fcfg):
    _, d = flows.run(_panel(rng), fcfg)
    assert d["coef"]["fpi"] == pytest.approx(-0.15, abs=0.02)
    assert d["coef"]["dxy"] == pytest.approx(0.5, abs=0.05)
    assert abs(d["t"]["fdi"]) < 3 and abs(d["t"]["brent"]) < 3


def test_contributions_add_up_to_the_actual_move(rng, fcfg):
    c, d = flows.run(_panel(rng), fcfg)
    parts = c.drop(columns="actual").sum(axis=1)
    np.testing.assert_allclose(parts, c["actual"])
    w = d["windows"]["3"]
    assert w["actual"] == pytest.approx(c["actual"].iloc[-3:].sum())
    assert sum(w[k] for k in ["fpi", "fdi", "dxy", "brent", "drift", "residual"]) == pytest.approx(w["actual"])


def test_out_of_window_fit_ignores_the_window(rng, fcfg):
    p = _panel(rng)
    _, d1 = flows.run(p, fcfg)
    p2 = p.copy()
    p2.iloc[-3:, p2.columns.get_loc("fpi_usd_mn")] *= 5      # change only the explained months' flows
    _, d2 = flows.run(p2, fcfg)
    o1, o2 = d1["windows"]["3"]["out_of_window"], d2["windows"]["3"]["out_of_window"]
    assert o2["fpi"] == pytest.approx(5 * o1["fpi"])          # same coefficient, five times the flow
    assert d2["coef"]["fpi"] != pytest.approx(d1["coef"]["fpi"])


def test_direction_flags_two_way_feedback(rng, fcfg):
    p = _panel(rng, n=400)
    inr = np.log(p["inr_usd"]).diff() * 100
    p["fpi_usd_mn"] = p["fpi_usd_mn"] - 1500 * inr.shift(1).fillna(0)   # investors sell after a fall
    d = flows.direction_tests(flows.frame(p), 3)
    assert d["inr_predicts_next_fpi"]["p"] < 0.05


def _with_rbi(p, rng, react=1.0):
    fpi_bn = p["fpi_usd_mn"] / 1000
    p["rbi_intervention_usd_mn"] = (react * fpi_bn + rng.normal(0, 1, len(p))) * 1000   # RBI offsets outflows
    p["rbi_fwd_book_usd_mn"] = -20000.0
    p["fx_reserves_usd_mn"] = 600000.0
    return p


def test_absorbed_pressure_is_the_dollar_price_times_rbi_sales(rng, fcfg):
    p = _with_rbi(_panel(rng), rng)
    c, d = flows.run(p, fcfg)
    iv, w = d["rbi"], d["rbi"]["windows"]["3"]
    assert iv["price_pct_per_bn"] == pytest.approx(-d["coef"]["fpi"])
    tail = c.iloc[-3:]
    assert w["absorbed"] == pytest.approx(-(iv["price_pct_per_bn"] * tail["rbi"]).sum())
    assert w["pressure"] == pytest.approx(w["actual"] + w["absorbed"])
    assert iv["reaction"]["coef"]["fpi"] == pytest.approx(1.0, abs=0.1)
    assert iv["fwd_book_pct_reserves"] == pytest.approx(-20000 / 600000 * 100)


def test_dollar_price_override(rng, fcfg):
    fcfg["models"]["flows"]["dollar_price"] = 0.3
    _, d = flows.run(_with_rbi(_panel(rng), rng), fcfg)
    assert d["rbi"]["price_pct_per_bn"] == 0.3 and d["rbi"]["price_source"] == "override"


def test_no_rbi_data_means_no_rbi_block(rng, fcfg):
    _, d = flows.run(_panel(rng), fcfg)
    assert d["rbi"] is None
