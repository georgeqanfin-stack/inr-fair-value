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
