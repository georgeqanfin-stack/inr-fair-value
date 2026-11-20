import pandas as pd
import pytest

from inrfv.data import ewn


def _workbook(path, extra_country="India"):
    df = pd.DataFrame({
        "Country": [extra_country, extra_country, "Korea", "Narnia"],
        "Year": [2023, 2024, 2024, 2024],
        "net IIP excl gold / GDP domestic currency": [-0.30, -0.343, 0.63, 0.1],
        "net IIP / GDP domestic currency": [-0.11, -0.096, 0.634, 0.1],
    })
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame({"x": ["intro"]}).to_excel(xw, sheet_name="Introduction", index=False)
        df.to_excel(xw, sheet_name="Dataset", index=False)


def test_parse_maps_names_and_scales_to_percent(tmp_path):
    _workbook(tmp_path / "ewn.xlsx")
    out = ewn.parse(tmp_path / "ewn.xlsx", ["IND", "KOR"])
    assert list(out["country"]) == ["IND", "IND", "KOR"]
    assert out.loc[1, "nfa_ewn"] == pytest.approx(-34.3)
    assert out.loc[1, "nfa_official"] == pytest.approx(-9.6)


def test_load_uses_cache_without_network_and_checks_coverage(tmp_path):
    pd.DataFrame({"country": ["IND"], "year": [2024], "nfa_ewn": [-34.3], "nfa_official": [-9.6]}
                 ).to_csv(tmp_path / "ewn_nfa.csv", index=False)
    assert ewn.load(["IND"], tmp_path)["nfa_ewn"].iloc[0] == -34.3
    with pytest.raises(ValueError, match="KOR"):
        ewn.load(["IND", "KOR"], tmp_path)


def test_parse_reads_the_october_2026_layout(tmp_path):
    """Oct 2026 release: lower-case "country", "date" instead of "Year", padded headers."""
    df = pd.DataFrame({"country": ["India ", "Korea"], "ifs_code": [534, 542], "date": [2025, 2025],
                       "net IIP excl gold / GDP domestic currency": [-0.339, 0.6],
                       " net IIP / GDP domestic currency": [-0.07, 0.6]})
    with pd.ExcelWriter(tmp_path / "new.xlsx") as xw:
        df.to_excel(xw, sheet_name="Dataset", index=False)
    out = ewn.parse(tmp_path / "new.xlsx", ["IND", "KOR"])
    assert list(out["country"]) == ["IND", "KOR"] and list(out["year"]) == [2025, 2025]
    assert out.loc[0, "nfa_ewn"] == pytest.approx(-33.9) and out.loc[0, "nfa_official"] == pytest.approx(-7.0)


def test_unreadable_new_workbook_falls_back_to_cache(tmp_path, monkeypatch):
    from inrfv.data import net
    pd.DataFrame({"country": ["IND"], "year": [2024], "nfa_ewn": [-34.3], "nfa_official": [-9.6]}
                 ).to_csv(tmp_path / "ewn_nfa.csv", index=False)
    (tmp_path / "x.xlsx").write_bytes(b"")
    monkeypatch.setattr(ewn, "latest_url", lambda: "https://example.org/x.xlsx")
    monkeypatch.setattr(ewn, "parse", lambda *a: (_ for _ in ()).throw(KeyError("Country")))
    net.reset()
    assert ewn.load(["IND"], tmp_path, refresh=True)["nfa_ewn"].iloc[0] == -34.3 and len(net.FALLBACKS) == 1
