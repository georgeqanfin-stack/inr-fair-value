import numpy as np
import pytest

from inrfv import note


@pytest.mark.parametrize("m,word", [(1.0, "close to"), (-3.0, "modestly"), (7.5, "moderately"), (12.4, "substantially")])
def test_size_word(m, word):
    assert note.size_word(m) == word


def test_verdict_sentence_direction_and_range():
    s = note.verdict_sentence(95.44, 84.91, 12.4, 79.5, 90.13)
    assert "undervalued" in s and "12.4% weaker" in s and "above the whole range" in s
    s = note.verdict_sentence(80.0, 84.0, -4.8, 79.0, 89.0)
    assert "overvalued" in s and "stronger" in s and "inside that range" in s
    assert "close to its composite fair value" in note.verdict_sentence(84.5, 84.0, 0.6, 80.0, 88.0)
    assert "Allowing" not in note.verdict_sentence(84.5, 84.0, 0.6, np.nan, np.nan)


def test_data_lines_group_by_source_and_report_revisions():
    diffs = {
        "dbie/bop.current_account.csv": {"new": 2, "new_range": ["2026-01", "2026-04"], "revised": 1,
                                         "max_revision": {"at": "2025-10", "before": -13198, "after": -12500, "pct": 5.3}},
        "dbie/bop.loans.csv": {"new": 2, "new_range": ["2026-01", "2026-04"], "revised": 0},
        "fred/DCOILBRENTEU.csv": {"new": 22, "new_range": ["2026-09-02", "2026-09-30"], "revised": 0},
    }
    lines = note.data_lines(diffs)
    bop = next(ln for ln in lines if "balance of payments" in ln)
    assert "4 new observations, now to Apr 2026" in bop and "largest 5.3% at Oct 2025" in bop
    assert any("FRED" in ln and "22 new" in ln for ln in lines)
    assert note.data_lines({}) == []
