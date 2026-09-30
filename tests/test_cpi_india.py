import numpy as np
import pandas as pd
import pytest

from inrfv.data.build import official_cpi_india


def _m(start, values):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


@pytest.fixture
def pieces():
    growth = lambda n, g, start: start * (1 + g) ** np.arange(n)
    return {
        # CPI-IW 1982 base to Dec 2005, 2001 base from Jan 2006 (factor 4.63 between them).
        "cpi.iw_1982": _m("2003-01-01", growth(36, 0.004, 500.0)),
        "cpi.iw_2001": _m("2006-01-01", growth(100, 0.005, 500.0 * 1.004 ** 36 / 4.63)),
        # CPI-C 2012 base from Jan 2013 to Dec 2025; back series Jan 2011 - May 2013.
        "cpi.combined_2012_bs": _m("2011-01-01", growth(29, 0.006, 90.0)),
        "cpi.combined_2012": _m("2013-01-01", growth(156, 0.004, 90.0 * 1.006 ** 24 * 1.01)),
    }


def test_segments_and_linking(pieces, cfg):
    mospi = _m("2025-01-01", np.linspace(101.0, 108.0, 20))
    level, src, yoy, meta = official_cpi_india(pieces, mospi, cfg)
    assert src["2010-12-01"] == "CPI-IW chained"
    assert src["2012-06-01"] == "MOSPI 2012 back series x LF"
    assert src["2020-06-01"] == "MOSPI 2012 x LF"
    assert src["2025-06-01"] == "MOSPI 2012 x LF"          # 2012 base is published through Dec 2025
    assert src["2026-03-01"] == "MOSPI 2024 (chained)"
    lf = cfg["cpi_india"]["linking_factor_2024"]
    assert level["2020-06-01"] == pytest.approx(pieces["cpi.combined_2012"]["2020-06-01"] * lf)
    # After the 2012 base ends, the level moves with the 2024 series month on month (no step).
    assert level["2026-03-01"] / level["2025-12-01"] == pytest.approx(mospi["2026-03-01"] / mospi["2025-12-01"])


def test_yoy_is_the_rate_published_at_the_time(pieces, cfg):
    mospi = _m("2025-01-01", np.linspace(101.0, 108.0, 20))
    _, _, yoy, _ = official_cpi_india(pieces, mospi, cfg)
    old = pieces["cpi.combined_2012"]
    # 2025: the 2012-base rate (the new series has no year-earlier value yet).
    assert yoy["2025-06-01"] == pytest.approx((old["2025-06-01"] / old["2024-06-01"] - 1) * 100)
    # 2026: the 2024-base rate.
    assert yoy["2026-03-01"] == pytest.approx((mospi["2026-03-01"] / mospi["2025-03-01"] - 1) * 100)
    # Before CPI-C: CPI-IW inflation, continuous across the 1982 -> 2001 base change.
    assert yoy["2006-06-01"] == pytest.approx(yoy["2005-06-01"], abs=0.7)
    assert yoy["2008-06-01"] == pytest.approx(((1.005 ** 12) - 1) * 100)


def test_cpi_iw_chain_joins_level_without_a_step(pieces, cfg):
    mospi = _m("2025-01-01", np.linspace(101.0, 108.0, 20))
    level, _, _, _ = official_cpi_india(pieces, mospi, cfg)
    mom = level.pct_change()
    # The first CPI-C month continues the CPI-IW path at a normal monthly rate.
    assert abs(mom["2011-01-01"]) < 0.02
    assert mom["2008-06-01"] == pytest.approx(0.005)


def test_missing_cpi_iw_overlap_raises(pieces, cfg):
    pieces["cpi.iw_2001"] = pieces["cpi.iw_2001"][:"2010-06-01"]
    with pytest.raises(ValueError):
        official_cpi_india(pieces, _m("2025-01-01", np.linspace(101.0, 108.0, 20)), cfg)
