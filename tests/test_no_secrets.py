"""Guard against committing credentials: the FRED key belongs in .env (git-ignored), never in a tracked file."""

import re
import subprocess

from conftest import ROOT, requires_git

KEYLIKE = re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*['\"]?([0-9a-f]{32}|[A-Za-z0-9_\-]{30,})")


@requires_git
def test_env_example_has_no_values():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            assert line.split("=", 1)[1].strip() == "", f".env.example must not hold a value: {line.split('=')[0]}"


@requires_git
def test_no_tracked_file_contains_a_key():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for f in files:
        if f.endswith((".xlsx", ".png", ".pdf", ".csv")):
            continue
        text = (ROOT / f).read_text(encoding="utf-8", errors="ignore")
        hits += [f for m in KEYLIKE.finditer(text) if "environ" not in text[max(0, m.start() - 40):m.start()]]
    assert not hits, f"possible credential in tracked files: {sorted(set(hits))}"
