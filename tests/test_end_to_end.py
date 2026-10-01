"""Full pipeline on the cached data in data/raw: report and dashboard are produced and consistent."""

import json
import re

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
