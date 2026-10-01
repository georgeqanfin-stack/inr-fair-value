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
