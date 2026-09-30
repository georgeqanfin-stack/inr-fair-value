"""Parsers for RBI DBIE Excel downloads.

Columns are located by their header text, not by fixed position: DBIE layouts
shift between downloads (the legacy notebooks read the SDR column as INR/USD
after one such shift). Each parser raises ``ParseError`` when a header it needs
is missing rather than silently returning the wrong column.
"""

from __future__ import annotations

import re
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
QUARTER_START = {"Q1": 4, "Q2": 7, "Q3": 10, "Q4": 1}   # Indian fiscal quarters


class ParseError(ValueError):
    pass


def _rows(path: Path) -> list[tuple]:
    # Not read_only: DBIE files carry wrong <dimension> metadata and read-only
    # mode silently drops the last column (the reserves 'US $ Millions' total).
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style")
        wb = openpyxl.load_workbook(path, data_only=True)
    try:
        return [tuple(r) for r in wb.active.iter_rows(values_only=True)]
    finally:
        wb.close()


def _norm(x) -> str:
    return re.sub(r"\s+", " ", str(x)).strip().lower() if x is not None else ""


def _find_row(rows, pred, what: str, start: int = 0) -> int:
    for i in range(start, len(rows)):
        if any(pred(_norm(c)) for c in rows[i]):
            return i
    raise ParseError(f"header not found: {what}")


def _find_col(row, pred, what: str, start: int = 0) -> int:
    for j in range(start, len(row)):
        if pred(_norm(row[j])):
            return j
    raise ParseError(f"column not found: {what}")


def _num(x) -> float:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else np.nan


def _month_start(dt: datetime) -> pd.Timestamp:
    return pd.Timestamp(year=dt.year, month=dt.month, day=1)


def _month_of(label) -> int | None:
    return MONTHS.get(_norm(label)[:3].upper()) if label else None


def _fy_calendar_year(fy_label: str, month: int) -> int:
    start = int(str(fy_label).strip().split("-")[0])
    return start if month >= 4 else start + 1


def _first_datetime(row) -> datetime | None:
    return next((c for c in row if isinstance(c, datetime)), None)


def parse_inr_usd(path: Path) -> pd.Series:
    """Monthly average INR per USD."""
    rows = _rows(path)
    h = _find_row(rows, lambda c: c == "us dollar", "'US Dollar'")
    col = _find_col(rows[h], lambda c: c == "us dollar", "'US Dollar'")
    if _norm(rows[h + 1][col]) != "average":
        raise ParseError("expected 'Average' under 'US Dollar'")
    data = {}
    for r in rows[h + 2:]:
        dt = _first_datetime(r)
        if dt is not None and not np.isnan(_num(r[col])):
            data[_month_start(dt)] = _num(r[col])
    return _series(data, "inr_usd")


def parse_reer(path: Path) -> pd.DataFrame:
    """Trade-weighted NEER and REER (RBI 40-currency basket)."""
    rows = _rows(path)
    h = _find_row(rows, lambda c: c == "trade-weighted", "'Trade-Weighted'")
    tw = _find_col(rows[h], lambda c: c == "trade-weighted", "'Trade-Weighted'")
    sub = rows[h + 1]
    neer = _find_col(sub, lambda c: c == "neer", "'NEER'", tw)
    reer = _find_col(sub, lambda c: c == "reer", "'REER'", tw)
    data = {}
    for r in rows[h + 2:]:
        dt = _first_datetime(r)
        if dt is not None and not np.isnan(_num(r[reer])):
            data[_month_start(dt)] = (_num(r[neer]), _num(r[reer]))
    df = pd.DataFrame.from_dict(data, orient="index", columns=["neer", "reer"]).sort_index()
    df.index.name = "date"
    return df


def parse_reserves(path: Path) -> pd.Series:
    """Total foreign exchange reserves, US$ million, end-month."""
    rows = _rows(path)
    h = _find_row(rows, lambda c: c == "total", "'Total'")
    ycol = _find_col(rows[h], lambda c: c == "year", "'Year'")
    mcol = _find_col(rows[h], lambda c: c == "month", "'Month'")
    tcol = _find_col(rows[h], lambda c: c == "total", "'Total'")
    ucol = _find_col(rows[h + 1], lambda c: c.startswith("us $"), "'US $ Millions' under Total", tcol)
    data, year = {}, None
    for r in rows[h + 2:]:
        y = str(r[ycol]).strip() if r[ycol] is not None else ""
        if re.fullmatch(r"\d{4}(\.0)?", y):
            year = int(float(y))
        m = _month_of(r[mcol]) if isinstance(r[mcol], str) else None
        if year and m and not np.isnan(_num(r[ucol])):
            data[pd.Timestamp(year=year, month=m, day=1)] = _num(r[ucol])
    return _series(data, "fx_reserves_usd_mn")


def parse_trade(path: Path) -> pd.DataFrame:
    """Merchandise exports and imports, US$ million (fiscal-year layout)."""
    rows = _rows(path)
    h = _find_row(rows, lambda c: c == "exports", "'Exports'")
    ycol = _find_col(rows[h], lambda c: c == "year", "'Year'")
    mcol = _find_col(rows[h], lambda c: c == "month", "'Month'")
    ecol = _find_col(rows[h], lambda c: c == "exports", "'Exports'")
    icol = _find_col(rows[h], lambda c: c == "imports", "'Imports'")
    data = {}
    for r in rows[h + 1:]:
        fy, m = r[ycol], _month_of(r[mcol]) if isinstance(r[mcol], str) else None
        if isinstance(fy, str) and "-" in fy and m:
            ex, im = _num(r[ecol]), _num(r[icol])
            if not (np.isnan(ex) or np.isnan(im)):
                data[pd.Timestamp(year=_fy_calendar_year(fy, m), month=m, day=1)] = (ex, im)
    df = pd.DataFrame.from_dict(data, orient="index", columns=["exports_usd_mn", "imports_usd_mn"])
    df.index.name = "date"
    return df.sort_index()


# BoP item code -> output column. Matched against header text "<code> <name>".
BOP_ITEMS = {
    "1": "current_account",
    "1.1": "merch_balance",
    "1.2.2.2": "private_transfers",
    "2": "capital_account",
    "2.1.1": "fdi_bop",
    "2.1.2": "portfolio_bop",
    "2.2": "loans",
    "2.3": "banking_capital",
    "4.2": "reserve_change",   # RBI sign: increase (-) / decrease (+)
}


def parse_bop_quarterly(path: Path) -> pd.DataFrame:
    """Quarterly BoP 'Net' rows, US$ million, stamped at the quarter's first month."""
    rows = _rows(path)
    h = _find_row(rows, lambda c: c == "transaction type", "'Transaction Type'")
    hdr = rows[h]
    fcol = _find_col(hdr, lambda c: c.startswith("year"), "'Year / Item'")
    qcol = _find_col(hdr, lambda c: c == "quarter", "'Quarter'")
    tcol = _find_col(hdr, lambda c: c == "transaction type", "'Transaction Type'")
    cols = {}
    for code, name in BOP_ITEMS.items():
        cols[name] = _find_col(hdr, lambda c, code=code: c.split(" ", 1)[0] == code, f"BoP item {code}")
    data = {}
    for r in rows[h + 1:]:
        fy, q, tx = r[fcol], r[qcol], r[tcol]
        if isinstance(fy, str) and "-" in fy and isinstance(q, str) and q.strip() in QUARTER_START \
                and _norm(tx) == "net":
            m = QUARTER_START[q.strip()]
            dt = pd.Timestamp(year=_fy_calendar_year(fy, m), month=m, day=1)
            data[dt] = {name: _num(r[j]) for name, j in cols.items()}
    df = pd.DataFrame.from_dict(data, orient="index").sort_index()
    df.index.name = "date"
    return df


def parse_foreign_investment_monthly(path: Path) -> pd.DataFrame:
    """Monthly net FDI and net portfolio investment, US$ million (from Mar 2011)."""
    rows = _rows(path)
    h = _find_row(rows, lambda c: c.startswith("b. net portfolio investment"), "'B. Net Portfolio Investment'")
    mcol = _find_col(rows[h], lambda c: c == "month", "'Month'")
    fdi = _find_col(rows[h], lambda c: c.startswith("a. net foreign direct investment"), "'A. Net FDI'")
    pf = _find_col(rows[h], lambda c: c.startswith("b. net portfolio investment"), "'B. Net Portfolio'")
    data = {}
    for r in rows[h + 1:]:
        m = re.match(r"\s*(\d{4}):(\d{2})", str(r[mcol] or ""))
        if m:
            data[pd.Timestamp(year=int(m[1]), month=int(m[2]), day=1)] = (_num(r[fdi]), _num(r[pf]))
    df = pd.DataFrame.from_dict(data, orient="index", columns=["fdi_usd_mn", "fpi_usd_mn"]).sort_index()
    df.index.name = "date"
    return df


def _series(data: dict, name: str) -> pd.Series:
    s = pd.Series(data, name=name, dtype=float).sort_index()
    s.index.name = "date"
    return s
