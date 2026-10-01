"""Full pipeline on the cached data in data/raw: report and dashboard are produced and consistent."""

import json
import re

import pandas as pd
import pytest

from conftest import RAW

pytestmark = pytest.mark.skipif(not (RAW / "MANIFEST.sha256").exists(), reason="cached raw data not present")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    from inrfv.config import load_config
    from inrfv.run import run_pipeline, save
    cfg = load_config()
    out = tmp_path_factory.mktemp("run")
    r = run_pipeline(cfg, refresh=False, run_dir=out)
    save(r, out)
    return r, out


def test_report_and_dashboard_written(run):
    r, out = run
    assert (out / "report.md").read_text(encoding="utf-8").startswith("# INR/USD fair value")
    html = (out / "dashboard.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "<title>Rupee Fair Value Monitor</title>" in html
    assert "__DATA__" not in html


def test_dashboard_data_matches_the_run(run):
    r, out = run
    html = (out / "dashboard.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))
    comp = r["composite"].dropna(subset=["ect"]).iloc[-1]
    assert data["fair"] == pytest.approx(comp["fair_inr"], abs=0.01)
    assert data["misalignment"] == pytest.approx(comp["misalignment_pct"], abs=0.05)
    assert data["corridor"][0] < data["fair"] < data["corridor"][1]
    assert len(data["series"]) == r["composite"]["ect"].notna().sum()
    assert {m["role"] for m in data["models"]} >= {"headline", "composite", "reported"}
    assert all(len(row) == 9 for row in data["series"])


def test_note_numbers_match_the_run(run):
    r, out = run
    text = (out / "note.md").read_text(encoding="utf-8")
    comp = r["composite"].dropna(subset=["ect"]).iloc[-1]
    assert f"{comp['fair_inr']:.2f}" in text and f"{abs(comp['misalignment_pct']):.1f}%" in text
    assert "monthly refresh" in text                      # plain runs do not claim a month-on-month comparison
    assert "[Dashboard](dashboard.html)" in text


def test_flow_attribution_reaches_every_output(run):
    r, out = run
    fd = r["flows_diag"]
    w = fd["windows"]["3"]
    assert sum(w[k] for k in fd["regressors"] + ["drift", "residual"]) == pytest.approx(w["actual"])
    assert "## Flow attribution" in (out / "report.md").read_text(encoding="utf-8")
    note = (out / "note.md").read_text(encoding="utf-8")
    assert "## What moved the rupee" in note and f"{abs(w['actual']):.1f}%" in note
    assert (out / "model_flows.csv").exists()
    html = (out / "dashboard.html").read_text(encoding="utf-8")
    assert '"flows":{"windows"' in html and 'id="flowBars"' in html


def test_dashboard_flow_values_round_like_the_note(run):
    r, out = run
    html = (out / "dashboard.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))
    w = r["flows_diag"]["windows"]["3"]
    for p in data["flows"]["windows"][0]["parts"]:
        assert f"{p['v']:+.1f}" == f"{w[p['key']]:+.1f}"


def test_rbi_intervention_is_point_in_time_and_reported(run):
    r, out = run
    ds = r["dataset"]
    col = "rbi_intervention_usd_mn"
    lag = r["config"]["publication_lag"]["rbi_intervention"]
    pd.testing.assert_series_equal(ds.pit[col], ds.panel[col].shift(lag).reindex(ds.pit.index), check_names=False)
    iv = r["flows_diag"]["rbi"]
    assert iv["reaction"]["coef"]["fpi"] > 0                      # the RBI leans against portfolio flows
    assert "### RBI intervention" in (out / "report.md").read_text(encoding="utf-8")
    assert "the RBI" in (out / "note.md").read_text(encoding="utf-8")


def test_market_pricing_is_reported(run):
    r, out = run
    mk = r["market"]
    obs = r["dataset"].panel["fwd_premium_3m"].last_valid_index().strftime("%Y-%m")
    assert mk["forwards"]["3m"]["month"] == obs                    # labelled with the month actually observed
    assert "## Market pricing" in (out / "report.md").read_text(encoding="utf-8")
    assert "forward market" in (out / "note.md").read_text(encoding="utf-8")
    assert "fwd" in r["beer_diag"]["specs"]                         # forward-based BEER spec is estimated


def test_revision_check_is_reported(run):
    r, out = run
    rv = r["revisions"]
    assert rv is not None and rv["n_months"] > 200
    assert (out / "revision_effect.csv").exists()
    assert "## Data revisions" in (out / "report.md").read_text(encoding="utf-8")
    assert "Data revisions" in (out / "note.md").read_text(encoding="utf-8")
    assert "cpi_us_vintage" in r["dataset"].meta


def test_imf_benchmark_is_reported(run):
    r, out = run
    bm = r["benchmark"]
    assert bm is not None and bm["n_years"] >= 9
    assert "## External benchmark" in (out / "report.md").read_text(encoding="utf-8")
    assert "IMF check" in (out / "dashboard.html").read_text(encoding="utf-8")
    assert "the IMF" in (out / "note.md").read_text(encoding="utf-8")


def test_peers_are_reported(run):
    r, out = run
    pe = r["peers"]
    assert pe["n"] >= 15 and 1 <= pe["focus_rank"] <= pe["n"]
    assert r["peer_gaps"]["IND"].dropna().round(6).equals(r["panel"]["misalignment_pct"].dropna().round(6))
    assert "## Peer currencies" in (out / "report.md").read_text(encoding="utf-8")
    assert 'id="peerBars"' in (out / "dashboard.html").read_text(encoding="utf-8")
    assert (out / "model_peers.csv").exists()


def test_composite_weights_are_tested_and_reported(run):
    r, out = run
    wt = r["weights"]
    assert wt["rule_choice"] == "equal" and wt["configured"] == "equal"     # data support the configured weights
    assert "### Composite weights" in (out / "report.md").read_text(encoding="utf-8")
    assert (out / "composite_weight_schemes.csv").exists()
