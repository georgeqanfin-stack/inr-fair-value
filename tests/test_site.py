import pytest
from conftest import ROOT

pytest.importorskip("markdown")

from inrfv import site  # noqa: E402


def test_relink_maps_documents_to_pages_and_the_rest_to_github():
    md = "[d](dashboard.html) [r](report.md) [m](../docs/METHODOLOGY.md#3-feer) [c](../config/default.toml) [i](fair_value.png)"
    out = site.relink(md)
    assert "(index.html)" in out and "(report.html)" in out and "(methodology.html#3-feer)" in out
    assert f"({site.REPO}/blob/main/config/default.toml)" in out and "(fair_value.png)" in out


def test_build_writes_every_page_with_working_internal_links(tmp_path):
    written = site.build(tmp_path / "site", ROOT)
    out = tmp_path / "site"
    assert written[0] == "index.html" and (out / ".nojekyll").exists()
    pages = {p for _, p, _ in site.PAGES}
    assert pages <= set(written)
    assert 'href="note.html"' in (out / "index.html").read_text(encoding="utf-8")       # links row on the dashboard
    for page in pages:
        text = (out / page).read_text(encoding="utf-8")
        assert "<table>" in text or page == "changes.html" or "<h1" in text
        for target in ("index.html", "note.html", "methodology.html"):
            assert f'href="{target}"' in text                                         # navigation on every page


def test_refresh_day_matches_the_workflow_schedule():
    import re
    import tomllib
    day = tomllib.loads((ROOT / "config" / "default.toml").read_text(encoding="utf-8"))["publication"]["refresh_day"]
    cron = re.search(r'cron: "(\S+) (\S+) (\S+) ', (ROOT / ".github" / "workflows" / "monthly-refresh.yml").read_text(encoding="utf-8"))
    assert cron and cron.group(1, 2) == ("0", "6") and int(cron.group(3)) == day


def test_latest_rate_is_injected_and_bad_prints_are_rejected(monkeypatch):
    from inrfv.data import latest
    page = "<html><script>\nconst D = {\"spot\":95.5};</script>"
    out = site.with_latest(page, {"rate": 92.68, "date": "2026-11-20", "source": "ECB"})
    assert out.index("INRFV_LATEST") < out.index("const D = ") and '"rate": 92.68' in out
    assert site.with_latest(page, None) == page
    monkeypatch.setattr(latest, "SOURCES", [("bad", lambda s: (60.0, "2026-11-20")), ("good", lambda s: (92.7, "2026-11-20"))])
    assert latest.fetch(reference=95.5, session=object())["source"] == "good"      # 60 is >10% off: skipped
    monkeypatch.setattr(latest, "SOURCES", [("down", lambda s: (_ for _ in ()).throw(OSError("timeout")))])
    assert latest.fetch(reference=95.5, session=object()) is None
