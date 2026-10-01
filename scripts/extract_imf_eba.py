"""Extract India's rows from the IMF "EBA estimates" PDFs into data/raw/manual/imf_eba_india.csv.

The PDFs (https://www.imf.org/external/np/res/eba/data.htm, "EBAEstimates-<year>.pdf") are
saved as data/raw/manual/imf_eba/EBAEstimates-analysis-<year>.pdf (git-ignored; re-download
to re-run). Each year has the same tables:

  Table 1   EBA Regression Analysis of <year> Current Accounts:
            actual CA, cyclical contribution, cyclically adjusted CA, CA norm, policy gaps,
            residual, total CA gap                       (% of GDP)
  REER-Index and REER-Level tables: first column = total REER gap (+ = overvalued)
  External Sustainability table: assumed CA/REER semi-elasticity (second-last column)

Also writes data/raw/manual/imf_eba_panel.csv: the same fields for the 11 panel
currencies the IMF assesses (long format, ISO3 codes), for the peer cross-section check.

Run:  python scripts/extract_imf_eba.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "manual" / "imf_eba"
OUT = ROOT / "data" / "raw" / "manual" / "imf_eba_india.csv"
OUT_PANEL = ROOT / "data" / "raw" / "manual" / "imf_eba_panel.csv"
NAMES = {"Brazil": "BRA", "China": "CHN", "India": "IND", "Indonesia": "IDN", "Korea": "KOR", "Malaysia": "MYS",
         "Mexico": "MEX", "Poland": "POL", "South Africa": "ZAF", "Thailand": "THA", "Turkey": "TUR", "Türkiye": "TUR"}
# Month each analysis became public: the External Sector Report of the following year
# (July; August in 2020 and 2021).
PUBLISHED = {2017: "2018-07", 2018: "2019-07", 2019: "2020-08", 2020: "2021-08", 2021: "2022-07",
             2022: "2023-07", 2023: "2024-07", 2024: "2025-07", 2025: "2026-07"}
PCT = re.compile(r"-?\d+(?:\.\d+)?%?")


def country_row(lines: list[str], name: str) -> list[float] | None:
    row = next((ln for ln in lines if re.match(rf"\s*{re.escape(name)}\s+-?\d", ln)), None)
    return None if row is None else [float(x.rstrip("%")) for x in PCT.findall(row.split(name, 1)[1])]


def extract(year: int, name: str = "India") -> dict | None:
    pages = [(p.extract_text() or "").splitlines() for p in PdfReader(SRC / f"EBAEstimates-analysis-{year}.pdf").pages]

    def table(pattern: str) -> list[float] | None:
        for lines in pages:
            title = next((ln for ln in lines if re.match(r"\s*Table\s+\d+", ln)), "")
            if re.search(pattern, title):
                row = country_row(lines, name)
                if row is not None:
                    return row
        return None

    ca = table(rf"EBA Regression Analysis of {year} Current Accounts")
    idx = table(r"REER-Index Model|Analysis of the \d{4} REER$|Analysis of the \d{4} REER\b(?!.*Level)")
    lvl = table(r"REER-Level Model|Level of the REER")
    es = table(r"External Sustainability")
    if ca is None or idx is None or lvl is None or es is None:
        if name == "India":
            raise ValueError(f"{year}: India rows not found")
        return None
    return {"analysis_year": year, "published": PUBLISHED[year],
            "ca_actual": ca[0], "ca_cyc_adj": ca[2], "ca_norm": ca[3], "ca_gap": ca[-1],
            "reer_gap_index": idx[0], "reer_gap_level": lvl[0], "elasticity": es[-2],
            "source": f"IMF EBA estimates: analysis of {year} (ESR {year + 1}), Table 1, REER-index, "
                      f"REER-level and external-sustainability tables"}


if __name__ == "__main__":
    years = [y for y in sorted(PUBLISHED) if (SRC / f"EBAEstimates-analysis-{y}.pdf").exists()]
    rows = [extract(y) for y in years]
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(pd.DataFrame(rows).drop(columns="source").to_string(index=False))
    panel = []
    for y in years:
        for name, iso in NAMES.items():
            rec = extract(y, name)
            if rec is not None:
                panel.append({"country": iso, **{k: v for k, v in rec.items() if k != "source"}})
    pd.DataFrame(panel).sort_values(["analysis_year", "country"]).to_csv(OUT_PANEL, index=False)
    print(pd.DataFrame(panel).groupby("analysis_year")["country"].apply(lambda s: " ".join(sorted(s))).to_string())
