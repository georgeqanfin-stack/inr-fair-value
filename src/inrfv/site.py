"""Static site for GitHub Pages, built from the published reports.

    python -m inrfv.site [--out _site]

The dashboard (reports/latest/dashboard.html) becomes the front page. The monthly note,
the full report, the refresh summary and the method documents are rendered from
Markdown to plain HTML pages beside it, with the charts and results.json copied
alongside, so every link between them works on the site. Nothing is computed here: the
site shows exactly what the last refresh published.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (source, page, title); sources under reports/latest unless given from the repo root.
PAGES = [
    ("reports/latest/note.md", "note.html", "Monthly note"),
    ("reports/latest/report.md", "report.html", "Full report"),
    ("reports/latest/refresh_summary.md", "changes.html", "What changed"),
    ("docs/METHODOLOGY.md", "methodology.html", "Methodology"),
    ("docs/REVIEW.md", "review.html", "Review write-up"),
]
ASSETS = ["fair_value.png", "oos_12m.png", "results.json", "composite_ect.csv"]
REPO = "https://github.com/georgeqanfin-stack/inr-fair-value"

STYLE = """
:root { --bg:#f7f8fa; --fg:#141a22; --muted:#5b6573; --rule:#dce1e7; --link:#1f5fbf; --code:#eef1f4; }
@media (prefers-color-scheme: dark) { :root { --bg:#0f1318; --fg:#e6e9ee; --muted:#9aa4b2; --rule:#2a313b;
  --link:#7fb0ff; --code:#1a2028; color-scheme: dark; } }
body { background:var(--bg); color:var(--fg); margin:0; font:16px/1.6 "IBM Plex Sans", system-ui, sans-serif; }
main { max-width:52rem; margin:0 auto; padding:1.5rem 1rem 4rem; }
nav { display:flex; flex-wrap:wrap; gap:.4rem 1.2rem; padding:.8rem 1rem; border-bottom:1px solid var(--rule);
  font-size:.9rem; max-width:52rem; margin:0 auto; }
a { color:var(--link); } nav a { text-decoration:none; } nav a[aria-current] { font-weight:600; color:var(--fg); }
h1, h2, h3 { line-height:1.25; text-wrap:balance; } h2 { margin-top:2.2rem; border-bottom:1px solid var(--rule); padding-bottom:.3rem; }
table { border-collapse:collapse; display:block; overflow-x:auto; font-size:.88rem; font-variant-numeric:tabular-nums; }
th, td { border:1px solid var(--rule); padding:.3rem .55rem; text-align:left; vertical-align:top; }
code { background:var(--code); padding:.1rem .3rem; border-radius:3px; font-size:.88em; }
pre { background:var(--code); padding:.8rem; overflow-x:auto; border-radius:4px; } pre code { padding:0; }
img { max-width:100%; } footer { color:var(--muted); font-size:.85rem; margin-top:3rem; }
"""


def nav(current: str) -> str:
    links = [("index.html", "Dashboard")] + [(page, title) for _, page, title in PAGES] + [(REPO, "Code")]
    return "<nav>" + "".join(
        f'<a href="{href}"{" aria-current=page" if href == current else ""}>{html.escape(t)}</a>' for href, t in links
    ) + "</nav>"


def relink(md_text: str) -> str:
    """Point links between published documents at their pages on the site."""
    names = {Path(src).name: page for src, page, _ in PAGES}
    names["dashboard.html"] = "index.html"

    def fix(m: re.Match) -> str:
        target, anchor = m.group(2), m.group(3) or ""
        name = Path(target).name
        if name in names and not target.startswith("http"):
            return f"{m.group(1)}({names[name]}{anchor})"
        if not target.startswith(("http", "#", "mailto:")) and name not in ASSETS:
            return f"{m.group(1)}({REPO}/blob/main/{target.lstrip('./').replace('../', '')}{anchor})"
        return m.group(0)

    return re.sub(r"(\[[^\]]*\])\(([^)#\s]+)(#[^)\s]*)?\)", fix, md_text)


def render(md_text: str, title: str, page: str) -> str:
    import markdown

    body = markdown.markdown(relink(md_text), extensions=["tables", "fenced_code", "toc"])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(title)} · USD/INR fair value</title><style>{STYLE}</style></head>"
            f"<body>{nav(page)}<main>{body}<footer>Published from <a href=\"{REPO}\">{REPO.split('/', 3)[3]}</a>. "
            f"Every figure comes from the last monthly refresh.</footer></main></body></html>\n")


def dashboard(text: str) -> str:
    """The dashboard with a links row after its footer."""
    links = " · ".join(f'<a href="{page}">{html.escape(t)}</a>' for _, page, t in PAGES)
    row = f'\n  <p style="text-align:center;font-size:.9rem;margin:1rem 0 2rem">{links} · <a href="{REPO}">Code</a></p>'
    marker = '<footer id="foot"></footer>'
    return text.replace(marker, marker + row, 1) if marker in text else text


def build(out: Path, root: Path = ROOT) -> list[str]:
    latest = root / "reports" / "latest"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written = ["index.html"]
    (out / "index.html").write_text(dashboard((latest / "dashboard.html").read_text(encoding="utf-8")), encoding="utf-8")
    for src, page, title in PAGES:
        p = root / src
        if p.exists():
            (out / page).write_text(render(p.read_text(encoding="utf-8"), title, page), encoding="utf-8")
            written.append(page)
    for a in ASSETS:
        if (latest / a).exists():
            shutil.copy2(latest / a, out / a)
            written.append(a)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m inrfv.site", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="_site", help="output directory (default _site)")
    args = ap.parse_args(argv)
    written = build(Path(args.out))
    print(f"wrote {len(written)} files to {args.out}: {', '.join(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
