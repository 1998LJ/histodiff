#!/usr/bin/env python3
"""A direct difflib -> histodiff migration, run side by side.

    python examples/migrate_from_difflib.py

This is meant to be read as much as run: the two functions below are a
realistic "print a unified diff of two files" helper, first written against
`difflib` the way most code already is, then the same function rewritten
against histodiff. The docstring on each line notes exactly what changed.
Run the script and it executes both against the same moved-function input
and prints the result of each, so you can see the migration is a drop-in
change to the *call*, not a rewrite of how your code thinks about diffing.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

try:
    import histodiff
except ImportError:  # not installed: use the checkout's src/ directory
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import histodiff


# --------------------------------------------------------------------------
# Before: difflib
# --------------------------------------------------------------------------


def render_diff_before(
    old_lines: list[str], new_lines: list[str], old_name: str, new_name: str
) -> str:
    """The kind of helper most codebases already have."""
    diff = difflib.unified_diff(old_lines, new_lines, old_name, new_name)
    return "".join(diff)


# --------------------------------------------------------------------------
# After: histodiff
# --------------------------------------------------------------------------


def render_diff_after(
    old_lines: list[str], new_lines: list[str], old_name: str, new_name: str
) -> str:
    """Same signature, same return value shape - only the two calls inside
    changed. Everything that called render_diff(...) needs no changes."""
    ops = histodiff.diff(old_lines, new_lines)  # was: difflib.unified_diff(...)
    diff = histodiff.unified_diff(ops, fromfile=old_name, tofile=new_name)
    return "".join(diff)


# --------------------------------------------------------------------------
# The other common pattern: difflib.SequenceMatcher directly
# --------------------------------------------------------------------------


def similarity_before(old_lines: list[str], new_lines: list[str]) -> float:
    """Code that uses SequenceMatcher's opcodes/ratio() directly - common in
    diff-review tools, dedup heuristics, "how similar are these two files"
    checks, etc."""
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    return matcher.ratio()


def similarity_after(old_lines: list[str], new_lines: list[str]) -> float:
    """The only change is the import - histodiff.SequenceMatcher is a real
    subclass of difflib.SequenceMatcher with the same methods, aligned with
    histodiff's algorithms instead of difflib's. get_opcodes(),
    get_grouped_opcodes(), and ratio() all just work."""
    # was: difflib.SequenceMatcher(None, old_lines, new_lines)
    matcher = histodiff.SequenceMatcher(None, old_lines, new_lines)
    return matcher.ratio()


# --------------------------------------------------------------------------
# Try both on an input difflib is known to mishandle: a moved function.
# --------------------------------------------------------------------------


def fetch_function(name: str) -> list[str]:
    # The docstring is deliberately identical across every function (as it
    # would be if it were copy-pasted, or generated) - that repetition,
    # past a couple hundred lines, is exactly what defeats difflib's
    # autojunk heuristic. See the README's "Why" section.
    return [
        f"def fetch_{name}(client, limit=100):\n",
        '    """Fetch a page of results from the API."""\n',
        "    results = []\n",
        f'    for page in client.paginate("/{name}", limit=limit):\n',
        "        results.extend(page)\n",
        "    return results\n",
        "\n",
        "\n",
    ]


def main() -> int:
    resources = [
        "users",
        "orders",
        "invoices",
        "payments",
        "refunds",
        "products",
        "carts",
        "reviews",
        "shipments",
        "coupons",
        "tickets",
        "sessions",
        "reports",
        "alerts",
        "teams",
        "projects",
        "tasks",
        "comments",
        "files",
        "webhooks",
        "events",
        "tags",
        "roles",
        "plans",
        "quotes",
        "leads",
    ]
    funcs = [fetch_function(name) for name in resources]
    old_lines = [line for func in funcs for line in func]
    # fetch_invoices moves from position 2 to the end, unchanged.
    moved = funcs[:2] + funcs[3:] + [funcs[2]]
    new_lines = [line for func in moved for line in func]

    before = render_diff_before(old_lines, new_lines, "old.py", "new.py")
    after = render_diff_after(old_lines, new_lines, "old.py", "new.py")

    def hunks(text: str) -> int:
        return sum(1 for line in text.splitlines() if line.startswith("@@"))

    def changed(text: str) -> int:
        return sum(
            1
            for line in text.splitlines()
            if line[:1] in "+-" and not line.startswith(("+++", "---"))
        )

    print("=== render_diff(): difflib.unified_diff -> histodiff.unified_diff ===")
    print(f"difflib   : {hunks(before)} hunks, {changed(before)} changed lines")
    print(f"histodiff : {hunks(after)} hunks, {changed(after)} changed lines")
    assert after == "".join(
        histodiff.unified_diff(
            histodiff.diff(old_lines, new_lines), fromfile="old.py", tofile="new.py"
        )
    )
    assert changed(after) * 3 < changed(before), "expected histodiff to win here"

    ratio_before = similarity_before(old_lines, new_lines)
    ratio_after = similarity_after(old_lines, new_lines)
    print()
    print("=== SequenceMatcher.ratio(): difflib -> histodiff ===")
    print(f"difflib.SequenceMatcher(...).ratio()   = {ratio_before:.3f}")
    print(f"histodiff.SequenceMatcher(...).ratio() = {ratio_after:.3f}")
    assert ratio_after > ratio_before, "expected histodiff to see these as more similar"

    print()
    print("Both migrations passed: same call shape, no changes needed by callers,")
    print("measurably better alignment on a moved function.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
