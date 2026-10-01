import numpy as np
import pandas as pd
import pytest

from inrfv.data import dbie
from inrfv.data.build import patch_inr_with_fred


def _rows(dates, values, **dims):
    return pd.DataFrame({"time_period": dates, "obs_value": values, **dims})


def test_monthly_dates_normalised_to_month_start():
    spec = dbie.Spec("x/y")
    s = dbie.to_series(_rows(["2026-05-30", "2026-06-30", "2026-07-31"], [1.0, 2.0, 3.0]), spec, "s")
    assert list(s.index.strftime("%Y-%m-%d")) == ["2026-05-01", "2026-06-01", "2026-07-01"]


def test_quarterly_stamped_at_indian_fiscal_quarter_start():
    spec = dbie.Spec("x/y", quarterly=True, scale=1e-6)
    s = dbie.to_series(_rows(["2025-09-30", "2025-12-31"], [-12_310e6, -13_198e6]), spec, "ca")
    # Q2 FY26 = Jul-Sep 2025, Q3 FY26 = Oct-Dec 2025: same convention as rbi.parse_bop_quarterly.
    assert list(s.index.strftime("%Y-%m-%d")) == ["2025-07-01", "2025-10-01"]
    assert s.iloc[0] == pytest.approx(-12_310)


def test_exact_duplicates_collapse_conflicting_raise():
    spec = dbie.Spec("x/y")
    s = dbie.to_series(_rows(["2026-01-31", "2026-01-31"], [5.3, 5.3]), spec, "s")
    assert len(s) == 1
    with pytest.raises(dbie.DbieError):
        dbie.to_series(_rows(["2026-01-31", "2026-01-31"], [5.3, 9.9]), spec, "s")


def test_empty_selection_raises():
    with pytest.raises(dbie.DbieError):
        dbie.to_series(pd.DataFrame(columns=["time_period", "obs_value"]), dbie.Spec("x/y"), "s")


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self._p


class _FakeSession:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return _FakeResponse(self.pages[len(self.calls) - 1])


def test_fetch_paginates_filters_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(dbie, "PAGE", 2)
    cols = ["time_period", "obs_value", "currency"]
    pages = [{"columns": cols, "rows": [["2026-01-31", 90.8, "USD"], ["2026-02-28", 90.7, "USD"]]},
             {"columns": cols, "rows": [["2026-03-31", 92.8, "USD"]]}]
    sess = _FakeSession(pages)
    s = dbie.fetch("inr_usd", tmp_path, refresh=True, session=sess)
    assert len(s) == 3 and s.iloc[-1] == pytest.approx(92.8)
    assert sess.calls[0]["currency"] == "USD" and sess.calls[1]["offset"] == 2
    # Second call reads the cache and makes no request.
    again = dbie.fetch("inr_usd", tmp_path, refresh=False, session=_FakeSession([]))
    pd.testing.assert_series_equal(s, again, check_freq=False, check_names=False)


def test_http_error_raises(tmp_path):
    with pytest.raises(dbie.DbieError):
        dbie.fetch("inr_usd", tmp_path, refresh=True, session=_FakeSession([{"error": "x"}]))


def _m(values, start="2025-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


def test_merge_prefers_later_vintage():
    api = _m([1, 2, 3, 4])                   # ends Apr
    xlsx = _m([1, 2, 30, 40, 50])            # ends May: the later release, with revisions
    merged = dbie.merge(api, xlsx)
    assert merged.tolist() == [1, 2, 30, 40, 50]
    api2 = _m([1, 2, 3, 4, 5, 6])            # now the API reaches further
    assert dbie.merge(api2, xlsx).tolist() == [1, 2, 3, 4, 5, 6]


def test_reconcile_separates_revisions_from_unexpected():
    old = _m(np.ones(36))
    new = old.copy()
    new.iloc[-2] = 1.5                        # recent revision
    new.iloc[3] = 2.0                         # old discrepancy: suspicious
    new = pd.concat([new, _m([1.0], "2028-01-01")])   # newer source reaches further
    r = dbie.reconcile(new, old, rel_tol=0.005, revision_window=12)
    assert r["newer_source"] == "api"
    assert r["n_revised"] == 1 and r["n_unexpected"] == 1


def test_monthly_gaps():
    s = _m([1, 2, 3, 4]).drop(pd.Timestamp("2025-02-01"))
    assert dbie.monthly_gaps(s) == ["2025-02"]


def test_inr_patch_fills_gap_and_extends_with_rescaled_fred():
    fred = _m(np.full(18, 100.0))
    rbi = _m(np.full(15, 101.0)).drop(pd.Timestamp("2026-02-01"))   # gap in Feb 2026, ends Mar 2026
    out, info = patch_inr_with_fred(rbi, fred, extend=True)
    assert info["filled"] == ["2026-02"]
    assert info["extended"] == ["2026-04", "2026-05", "2026-06"]
    assert out["2026-02-01"] == pytest.approx(101.0)                  # rescaled to RBI's level
    assert out["2026-06-01"] == pytest.approx(101.0)
    out2, info2 = patch_inr_with_fred(rbi, fred, extend=False)
    assert info2["extended"] == [] and out2.index.max() == rbi.index.max()


def test_series_specs_cover_every_bop_item():
    from inrfv.data.rbi import BOP_ITEMS
    assert {f"bop.{v}" for v in BOP_ITEMS.values()} <= set(dbie.SERIES)


def _bulletin_rows(sale_mar=1680.0):
    head = {"c1": "Month", "c3": "1 Net Purchase/ Sale of Foreign Currency (US $ Millions)", "c4": "1.1 Purchase (+)",
            "c5": "1.2 Sale (-)", "c9": "4 Outstanding Net Forward Sales (-)/ Purchase (+) at the end of month"}
    rows = [{"tab": "Sale/Purchase of USD by RBI", **head},
            {"tab": "Sale/Purchase of USD by RBI", "c1": "April", "c2": "2014", "c3": "5,870", "c4": "7,850", "c5": "1,980", "c9": "-32,062"},
            {"tab": "Sale/Purchase of USD by RBI", "c1": "March", "c2": "2014", "c3": "7782.00", "c4": "9462.00", "c5": str(sale_mar), "c9": "-31,030"},
            {"tab": "Sale/Purchase of USD by RBI", "c1": "February", "c2": "2014", "c3": "-530", "c4": "-", "c5": "530", "c9": "-1,39,197"},
            {"tab": "ii) Operations in currency futures segment", "c1": "March", "c2": "2014", "c3": "999"}]
    return pd.DataFrame(rows).reindex(columns=["tab"] + [f"c{i}" for i in range(1, 10)])


def test_parse_intervention_reads_indian_grouping_and_dashes():
    out = dbie.parse_intervention(_bulletin_rows())
    assert list(out.index.strftime("%Y-%m")) == ["2014-02", "2014-03", "2014-04"]
    assert out.loc["2014-02-01", "purchase"] == 0 and out.loc["2014-02-01", "fwd_book"] == -139197
    assert not out["gross_fixed"].any()


def test_parse_intervention_rebuilds_a_bad_gross_leg_from_the_net():
    out = dbie.parse_intervention(_bulletin_rows(sale_mar=9462.0))     # RBI's Mar 2014 typo
    assert out.loc["2014-03-01", "sale"] == 1680 and out.loc["2014-03-01", "gross_fixed"]


def test_parse_intervention_fails_on_layout_change():
    rows = _bulletin_rows()
    rows.loc[0, "c9"] = "something else"
    with pytest.raises(dbie.DbieError, match="layout"):
        dbie.parse_intervention(rows)


def _bpm6_rows():
    head = ["Item", "Jan-Mar 2026 (P)", None, None, "Oct-Dec 2025 (P)", None, None]
    sub = [None, "Credit", "Debit", "Net", "Credit", "Debit", "Net"]
    items = {"1 Current Account": (280, 274, 6), "1.A.a Goods": (113, 197, -84), "1.A.b Services": (111, 51, 60), "1.B Primary Income": (12, 24, -12),
             "1.C.1 Financial corporations": (44, 3, 41), "2 Capital Account": (0, 0, 0.07),
             "3 Financial Account": (250, 257, -7), "3.1 Direct Investment": (23, 19, 4),
             "3.2 Portfolio Investment": (125, 138, -13), "3.5 Reserve assets": ("-", 7, -7)}
    rows = [["Standard Presentation of India's Balance of Payments As Per BPM6- Quarterly - US Dollar"] + [None] * 6,
            head, sub, ["", "2", "3", "4", "5", "6", "7"]]
    for lab, (c, d, n) in items.items():
        rows.append([lab, str(c), str(d), str(n), str(c), str(d), "1,00,000" if lab.startswith("1 ") else str(n)])
    df = pd.DataFrame(rows, columns=[f"c{i}" for i in range(1, 8)])
    df.insert(0, "row_no", range(1, len(df) + 1))
    return df


def test_parse_bop_bpm6_maps_items_and_quarters():
    out = dbie.parse_bop_bpm6(_bpm6_rows())
    assert list(out.index.strftime("%Y-%m")) == ["2025-10", "2026-01"]
    q = out.loc["2026-01-01"]
    assert q["current_account"] == 6 and q["merch_balance"] == -84 and q["goods_debit"] == 197
    assert q["reserve_change"] == -7
    assert q["capital_account"] == pytest.approx(0.07 + -7 - -7)          # 2 + 3 - 3.5
    assert out.loc["2025-10-01", "current_account"] == 100000             # Indian digit grouping


def test_parse_bop_bpm6_fails_on_missing_item():
    rows = _bpm6_rows()
    rows = rows[~rows["c1"].astype(str).str.startswith("3.1 ")]
    with pytest.raises(dbie.DbieError, match="3.1"):
        dbie.parse_bop_bpm6(rows)


def test_parse_cpi_2024_reads_general_index_and_flags():
    rows = pd.DataFrame([
        {"tab": "CPI - 2024=100 (All India)", "c1": "Base : 2024 = 100"},
        {"tab": "CPI - 2024=100 (All India)", "c1": "AUG-2026", "c2": "A) General Index", "c3": "Provisional", "c8": "108.74", "c9": "4.82"},
        {"tab": "CPI - 2024=100 (All India)", "c1": "AUG-2026", "c2": "01 Food and beverages", "c3": "Provisional", "c8": "110.37", "c9": "5.66"},
        {"tab": "CPI - 2024=100 (All India)", "c1": "DEC-2025", "c2": "A) General Index", "c3": "Final", "c8": "104.10", "c9": ""},
        {"tab": "CPI - 2012=100 (All India)", "c1": "AUG-2026", "c2": "A) General Index", "c3": "Final", "c8": "999", "c9": "1"},
    ])
    out = dbie.parse_cpi_2024(rows)
    assert list(out.index.strftime("%Y-%m")) == ["2025-12", "2026-08"]
    assert out.loc["2026-08-01", "index"] == 108.74 and out.loc["2026-08-01", "provisional"]
    assert pd.isna(out.loc["2025-12-01", "inflation"])


def test_monthly_from_daily_drops_the_unfinished_month():
    d = pd.Series(1.0, index=pd.date_range("2026-08-03", "2026-10-02", freq="B"))
    out = dbie.monthly_from_daily(d, today=pd.Timestamp("2026-10-02"))
    assert list(out.index.strftime("%Y-%m")) == ["2026-08", "2026-09"]


def test_parse_gdp_new_base_fiscal_quarters():
    rows = pd.DataFrame([
        {"tab": "NAS : 2022-23", "row_no": "1", "c1": "Item/ Year", "c2": "Quarter", "c3": "1. PFCE", "c4": "9. Gross Domestic Product"},
        {"tab": "NAS : 2022-23", "row_no": "2", "c1": "2025-26", "c2": "Q1", "c3": "1", "c4": "75,46,230.00"},
        {"tab": "NAS : 2022-23", "row_no": "3", "c1": None, "c2": "Q2", "c3": "1", "c4": "75,41,258.00"},
        {"tab": "NAS : 2022-23", "row_no": "4", "c1": None, "c2": "Q4", "c3": "1", "c4": "88,80,334.00"},
        {"tab": "NAS : 2011-12", "row_no": "5", "c1": "2025-26", "c2": "Q1", "c3": "1", "c4": "1"},
    ])
    s = dbie.parse_gdp_new_base(rows)
    assert list(s.index.strftime("%Y-%m")) == ["2025-04", "2025-07", "2026-01"]
    assert s.iloc[0] == 7546230.0
