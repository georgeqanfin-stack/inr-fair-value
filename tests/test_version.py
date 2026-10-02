import re
import tomllib

from conftest import ROOT

import inrfv


def test_one_version_everywhere():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert inrfv.__version__ == pyproject
    major_minor = ".".join(pyproject.split(".")[:2])
    assert re.search(rf"\*\*Version {re.escape(major_minor)}\.\*\*", readme)
    assert f"| {major_minor} |" in changelog
