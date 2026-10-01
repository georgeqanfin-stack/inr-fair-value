import pandas as pd
from conftest import RAW

from inrfv.data import schemas


def test_cached_inputs_pass_their_schemas():
    if not RAW.exists():
        return
    assert schemas.validate(RAW) == []


def _write(tmp_path, rel, df):
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False)


def test_schema_catches_format_changes(tmp_path):
    dates = pd.date_range("2000-01-01", periods=400, freq="MS").strftime("%Y-%m-%d")
    _write(tmp_path, "dbie/inr_usd.csv", pd.DataFrame({"date": dates, "rate": 80.0}))                 # renamed column
    _write(tmp_path, "dbie/reer.csv", pd.DataFrame({"date": list(dates[:-1]) + [dates[0]], "value": 100.0}))   # duplicate
    _write(tmp_path, "dbie/fx_reserves_usd_mn.csv", pd.DataFrame({"date": dates, "value": 600.0e6}))   # wrong units
    _write(tmp_path, "fred/X.csv", pd.DataFrame({"date": ["2020-01-01", "not a date"], "value": [1, "abc"]}))
    problems = schemas.validate(tmp_path)
    text = "\n".join(problems)
    assert "inr_usd.csv: columns" in text
    assert "reer.csv: 1 duplicated keys" in text
    assert "fx_reserves_usd_mn.csv: 400 values of 'value' outside" in text
    assert "X.csv: 1 unparseable dates" in text and "X.csv: 1 non-numeric values" in text


def test_unknown_files_in_subfolders_are_not_silently_skipped_for_known_patterns(tmp_path):
    _write(tmp_path, "dbie/new_series.csv", pd.DataFrame({"date": ["2020-01-01"], "value": [1.0]}))
    assert schemas.rule_for("dbie/new_series.csv") is schemas.DV
    assert schemas.validate(tmp_path) == []
