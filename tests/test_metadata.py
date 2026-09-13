from importlib.metadata import version
from pathlib import Path

import histodiff


def test_package_version_matches_distribution_metadata() -> None:
    assert histodiff.__version__ == version("histodiff")


def test_changelog_contains_package_version() -> None:
    changelog = Path(__file__).parents[1] / "CHANGELOG.md"
    assert f"## [{histodiff.__version__}]" in changelog.read_text(encoding="utf-8")
