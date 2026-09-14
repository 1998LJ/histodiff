#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md, for use as release notes.

Usage:
    python scripts/changelog_section.py 0.1.0

Used by the Release workflow to put the changelog's own entry for the
version being tagged directly into the GitHub Release body, rather than
just linking to CHANGELOG.md.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: changelog_section.py VERSION", file=sys.stderr)
        return 2
    version = sys.argv[1]

    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # A version's section runs from its own "## [VERSION] ..." heading up to
    # (not including) whichever comes first: the next "## [" heading, the
    # trailing block of "[label]: https://..." reference links Keep a
    # Changelog puts at the end of the file, or the end of the file itself.
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]:|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        print(
            f"no CHANGELOG.md section found for version {version!r} "
            f"(looked for a line starting with '## [{version}]')",
            file=sys.stderr,
        )
        return 1

    section = match.group(1).strip()
    if not section:
        print(f"CHANGELOG.md section for {version!r} is empty", file=sys.stderr)
        return 1

    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
