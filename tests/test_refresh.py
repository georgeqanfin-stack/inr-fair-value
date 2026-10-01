from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from inrfv import refresh as rf


def _write(p: Path, dates, values):
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": dates, "value": values}).to_csv(p, index=False)


def test_diff_detects_new_revised_and_lost(tmp_path):
    raw = tmp_path / "raw"
    _write(raw / "fred" / "A.csv", ["2026-01-01", "2026-02-01", "2026-03-01"], [1.0, 2.0, 3.0])
    _write(raw / "fred" / "B.csv", ["2026-01-01", "2026-02-01"], [5.0, 6.0])
    before = rf.snapshot(raw)
    _write(raw / "fred" / "A.csv", ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"], [1.0, 2.2, 3.0, 4.0])
    _write(raw / "fred" / "B.csv", ["2026-02-01"], [6.0])
    d = rf.diff_snapshots(before, rf.snapshot(raw))
    assert d["fred/A.csv"]["new"] == 1 and d["fred/A.csv"]["new_range"] == ["2026-04", "2026-04"]
    assert d["fred/A.csv"]["revised"] == 1
    assert d["fred/A.csv"]["max_revision"]["at"] == "2026-02"
    assert d["fred/B.csv"]["lost"] == 1


def test_unchanged_files_are_not_reported(tmp_path):
    raw = tmp_path / "raw"
    _write(raw / "dbie" / "x.csv", ["2026-01-01"], [1.0])
    s = rf.snapshot(raw)
    assert rf.diff_snapshots(s, rf.snapshot(raw)) == {}


def test_panel_and_legacy_date_formats_are_read(tmp_path):
    p = tmp_path / "wb_x.csv"
    pd.DataFrame({"": ["01-01-2023", "01-01-2024"], "v": [1.0, 2.0]}).to_csv(p, index=False)
    s = rf.read_cached(p)
    assert list(s.index.year) == [2023, 2024]
    q = tmp_path / "panel.csv"
    pd.DataFrame({"country": ["IND", "CHN"], "year": [2024, 2024], "value": [1.0, 2.0]}).to_csv(q, index=False)
    assert rf.read_cached(q).loc[("IND", 2024)] == 1.0


@pytest.mark.parametrize("today,expected", [(date(2026, 10, 1), "2026-08"), (date(2026, 10, 13), "2026-09"),
                                            (date(2026, 1, 5), "2025-11")])
def test_expected_mospi_month(today, expected):
    assert rf.expected_mospi_month(today).strftime("%Y-%m") == expected


def test_gates_fail_on_lost_history_and_implausible_jumps(cfg):
    idx = pd.date_range("2020-01-01", periods=12, freq="MS")
    inr = pd.Series(80.0, index=idx)
    inr.iloc[-1] = 120.0                                          # +40% in one month: a unit or parsing error
    ds = SimpleNamespace(panel=pd.DataFrame({"inr_usd": inr, "reer": 100.0, "dxy": 100.0}, index=idx), meta={})
    diffs = {"dbie/inr_usd.csv": {"new": 1, "new_range": ["2020-12", "2020-12"], "lost": 0, "revised": 0},
             "fred/X.csv": {"new": 0, "lost": 2, "revised": 0, "lost_examples": ["2001-01"]}}
    failures, _ = rf.quality_gates(cfg, diffs, ds, date(2026, 10, 1))
    assert any("disappeared" in f for f in failures)
    assert any("inr_usd" in f and "plausibility" in f for f in failures)


def test_refresh_restores_data_when_a_fetch_fails(tmp_path, cfg, monkeypatch):
    raw = tmp_path / "raw"
    _write(raw / "fred" / "A.csv", ["2026-01-01"], [1.0])
    original = (raw / "fred" / "A.csv").read_bytes()
    cfg["paths"]["raw"] = str(raw)
    cfg["paths"]["runs"] = str(tmp_path / "outputs" / "runs")

    def broken_fetch(cfg, refresh):
        (raw / "fred" / "A.csv").write_text("garbage")          # a half-written download
        raise ConnectionError("network down")

    monkeypatch.setattr(rf, "build_dataset", broken_fetch)
    assert rf.refresh(cfg, today=date(2026, 10, 1)) == 2
    assert (raw / "fred" / "A.csv").read_bytes() == original


def test_headline_change_decomposes_by_component(tmp_path, cfg):
    idx = pd.date_range("2026-01-01", periods=3, freq="MS")
    old = pd.DataFrame({"inr_usd": 90.0, "fair_inr": 85.0, "misalignment_pct": 5.0, "ect": 0.05,
                        "gap_reer": 0.04, "gap_feer": 0.06}, index=idx)
    old.to_csv(tmp_path / "composite_ect.csv")
    new_idx = pd.date_range("2026-01-01", periods=4, freq="MS")
    new = pd.DataFrame({"inr_usd": 92.0, "fair_inr": 84.0, "misalignment_pct": 9.0, "ect": 0.09,
                        "gap_reer": 0.10, "gap_feer": 0.08}, index=new_idx)
    ch = rf.headline_change(tmp_path, new, cfg)
    assert ch["previous_asof"] == "2026-03" and ch["asof"] == "2026-04"
    assert ch["misalignment_pct"] == [5.0, 9.0]
    # Equal weights: REER +6pp x 0.5 = +3.0, FEER +2pp x 0.5 = +1.0.
    assert ch["contribution_pp"]["REER component"] == pytest.approx(3.0)
    assert ch["contribution_pp"]["FEER"] == pytest.approx(1.0)
