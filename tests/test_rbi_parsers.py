from datetime import datetime

import openpyxl
import pytest

from inrfv.data import rbi
from conftest import RAW


def _write(tmp_path, rows, name="f.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(list(r))
    p = tmp_path / name
    wb.save(p)
    return p


def test_inr_usd_found_by_header_not_position(tmp_path):
    # An extra leading column shifts everything right: position-based parsing
    # would read the SDR column. Header-based parsing must still find US Dollar.
    rows = [
        (None, None, "Year/Month", "SDR", None, "US Dollar", None),
        (None, None, None, "Average", "End-month", "Average", "End-month"),
        (None, datetime(2026, 4, 30), "Apr-2026", 128.1, 130.7, 93.55, 95.2),
        (None, datetime(2026, 3, 31), "Mar-2026", 126.3, 128.5, 92.76, 94.7),
    ]
    s = rbi.parse_inr_usd(_write(tmp_path, rows))
    assert s.loc["2026-04-01"] == pytest.approx(93.55)
    assert s.index.is_monotonic_increasing


def test_missing_header_raises(tmp_path):
    rows = [(None, "Year/Month", "SDR", None), (None, None, "Average", "End-month")]
    with pytest.raises(rbi.ParseError):
        rbi.parse_inr_usd(_write(tmp_path, rows))


def test_bop_fiscal_quarter_dating(tmp_path):
    hdr = (None, "Year / Item", "Quarter", "Transaction Type", "Overall", "1 CURRENT ACCOUNT (1.1+ 1.2)",
           "1.1 MERCHANDISE", "1.2.2.2 Private", "2 CAPITAL ACCOUNT", "2.1.1 Foreign Direct Investment",
           "2.1.2 Portfolio Investment", "2.2 Loans (2.2.1)", "2.3 Banking Capital",
           "4.2 Foreign Exchange Reserves (Increase - / Decrease +)")
    rows = [hdr,
            (None, "2025-26", "Q3", "Credit") + (1,) * 10,
            (None, "2025-26", "Q3", "Net", -24409, -13198, -93629, 35367, -10005, -3659, -177, 13317, 692, 24409),
            (None, "2025-26", "Q4", "Net") + (0,) * 10]
    df = rbi.parse_bop_quarterly(_write(tmp_path, rows))
    assert df.loc["2025-10-01", "current_account"] == -13198       # Q3 FY26 = Oct-Dec 2025
    assert "2026-01-01" in df.index.strftime("%Y-%m-%d")            # Q4 FY26 = Jan-Mar 2026
    assert len(df) == 2                                             # Credit rows ignored


needs_raw = pytest.mark.skipif(not (RAW / "rbi_inr_usd.xlsx").exists(), reason="raw RBI files not present")


@needs_raw
def test_real_files_known_values():
    assert rbi.parse_inr_usd(RAW / "rbi_inr_usd.xlsx").loc["2026-04-01"] == pytest.approx(93.5502, abs=1e-3)
    assert rbi.parse_reer(RAW / "rbi_reer.xlsx").loc["2026-04-01", "reer"] == pytest.approx(90.958, abs=1e-3)
    assert rbi.parse_reserves(RAW / "rbi_reserves.xlsx").loc["2026-02-01"] == pytest.approx(728493.828)
    bop = rbi.parse_bop_quarterly(RAW / "rbi_cab.xlsx")
    assert bop.loc["2025-10-01", "current_account"] == pytest.approx(-13197.8, abs=0.1)
    assert bop.loc["2025-10-01", "reserve_change"] == pytest.approx(24408.7, abs=0.1)
    fi = rbi.parse_foreign_investment_monthly(RAW / "rbi_fpi_flows.xlsx")
    assert fi.loc["2026-03-01", "fpi_usd_mn"] == pytest.approx(-13342.59, abs=0.01)
    tr = rbi.parse_trade(RAW / "rbi_trade.xlsx")
    assert tr.loc["2026-03-01", "exports_usd_mn"] == pytest.approx(38918.61, abs=0.01)
