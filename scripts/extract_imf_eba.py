"""Extract India's rows from the IMF "EBA estimates" PDFs into data/raw/manual/imf_eba_india.csv.

The PDFs (https://www.imf.org/external/np/res/eba/data.htm, "EBAEstimates-<year>.pdf") are
saved as data/raw/manual/imf_eba/EBAEstimates-analysis-<year>.pdf (git-ignored; re-download
to re-run). Each year has the same tables:

  Table 1   EBA Regression Analysis of <year> Current Accounts:
            actual CA, cyclical contribution, cyclically adjusted CA, CA norm, policy gaps,
            residual, total CA gap                       (% of GDP)
  REER-Index and REER-Level tables: first column = total REER gap (+ = overvalued)
  External Sustainability table: assumed CA/REER semi-elasticity (second-last column)

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
# Month each analysis became public: the External Sector Report of the following year
# (July; August in 2020 and 2021).
PUBLISHED = {2017: "2018-07", 2018: "2019-07", 2019: "2020-08", 2020: "2021-08", 2021: "2022-07",
             2022: "2023-07", 2023: "2024-07", 2024: "2025-07", 2025: "2026-07"}
PCT = re.compile(r"-?\d+(?:\.\d+)?%?")


def india_row(lines: list[str]) -> list[float]:
    row = next(l for l in lines if l.strip().startswith("India"))
    return [float(x.rstrip("%")) for x in PCT.findall(row.split("India", 1)[1])]


def extract(year: int) -> dict:
    pages = [(p.extract_text() or "").splitlines() for p in PdfReader(SRC / f"EBAEstimates-analysis-{year}.pdf").pages]

    def table(pattern: str) -> list[float]:
        for lines in pages:
            title = next((l for l in lines if re.match(r"\s*Table\s+\d+", l)), "")
            if re.search(pattern, title) and any(l.strip().startswith("India") for l in lines):
                return india_row(lines)
        raise ValueError(f"{year}: no table matching {pattern!r}")

    ca = table(rf"EBA Regression Analysis of {year} Current Accounts")
    idx = table(r"REER-Index Model|Analysis of the \d{4} REER$|Analysis of the \d{4} REER\b(?!.*Level)")
    lvl = table(r"REER-Level Model|Level of the REER")
    es = table(r"External Sustainability")
    return {"analysis_year": year, "published": PUBLISHED[year],
            "ca_actual": ca[0], "ca_cyc_adj": ca[2], "ca_norm": ca[3], "ca_gap": ca[-1],
            "reer_gap_index": idx[0], "reer_gap_level": lvl[0], "elasticity": es[-2],
            "source": f"IMF EBA estimates: analysis of {year} (ESR {year + 1}), Table 1, REER-index, "
                      f"REER-level and external-sustainability tables"}


if __name__ == "__main__":
    rows = [extract(y) for y in sorted(PUBLISHED) if (SRC / f"EBAEstimates-analysis-{y}.pdf").exists()]
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(pd.DataFrame(rows).drop(columns="source").to_string(index=False))
