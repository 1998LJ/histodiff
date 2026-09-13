#!/usr/bin/env python3
"""difflib vs histodiff on the same inputs, side by side.

Run from a checkout (installing is optional):

    python examples/before_after.py            # first 24 diff lines per scenario
    python examples/before_after.py --full     # complete diffs

Both sides are rendered by the same unified-diff formatter, so every
difference you see comes from how the lines were *aligned*. difflib is used
exactly as ``difflib.unified_diff`` uses it: ``SequenceMatcher`` with its
default heuristics, which ``unified_diff`` gives you no way to turn off.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

try:
    import histodiff
except ImportError:  # not installed: use the checkout's src/ directory
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import histodiff

COLUMN = 52


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

RESOURCES = [
    "users", "orders", "invoices", "payments", "refunds", "products", "carts",
    "reviews", "shipments", "coupons", "tickets", "sessions", "reports",
    "alerts", "teams", "projects", "tasks", "comments", "files", "webhooks",
    "events", "tags", "roles", "plans", "quotes", "leads", "notes", "badges",
    "vendors", "regions",
]


def fetch_function(name: str) -> list[str]:
    return [
        f"def fetch_{name}(client, limit=100):",
        f'    """Return up to `limit` {name} from the API."""',
        "    results = []",
        f'    for page in client.paginate("/{name}", limit=limit):',
        "        results.extend(page)",
        "    return results",
        "",
        "",
    ]


def moved_function() -> tuple[list[str], list[str]]:
    """`fetch_orders` moves from the top of a 240-line module to the bottom."""
    funcs = [fetch_function(name) for name in RESOURCES]
    old = sum(funcs, [])
    new = sum(funcs[:1] + funcs[2:] + funcs[1:2], [])
    return old, new


def unique_row() -> tuple[list[str], list[str]]:
    """One non-zero reading inserted into a mostly-zero 300-row CSV."""
    old = ["0,0,0,0,0,0,0,0"] * 300
    new = old[:150] + ["0,0,0,7,0,0,0,0"] + old[150:]
    return old, new


def config_section(name: str, port: int) -> list[str]:
    return [f"[{name}]", "enabled = true", f"port = {port}", "timeout = 30",
            "retries = 3", ""]


SERVICES = ["api", "web", "worker", "cron", "cache", "db"]


def reordered_sections() -> tuple[list[str], list[str]]:
    """The [cache] section moves up in a small INI file full of repeated keys."""
    sections = {n: config_section(n, 8000 + i) for i, n in enumerate(SERVICES)}
    old = sum((sections[n] for n in SERVICES), [])
    order = ["api", "cache", "web", "worker", "cron", "db"]
    new = sum((sections[n] for n in order), [])
    return old, new


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def difflib_ops(old: list[str], new: list[str]) -> list[histodiff.DiffOp]:
    """difflib's alignment, as DiffOps, so both sides share one formatter."""
    matcher = difflib.SequenceMatcher(None, old, new)
    return [
        histodiff.DiffOp(tag, i1, i2, j1, j2, tuple(old[i1:i2]), tuple(new[j1:j2]))
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    ]


def render(ops: list[histodiff.DiffOp]) -> list[str]:
    return list(histodiff.unified_diff(ops, lineterm=""))[2:]  # skip ---/+++


def stats(ops: list[histodiff.DiffOp]) -> tuple[int, int]:
    lines = render(ops)
    hunks = sum(line.startswith("@@") for line in lines)
    changed = sum(line[:1] in "+-" for line in lines)
    return hunks, changed


def clip(text: str) -> str:
    return text if len(text) <= COLUMN else text[: COLUMN - 1] + "~"


def side_by_side(left: list[str], right: list[str], limit: int | None) -> None:
    rows = max(len(left), len(right))
    shown = rows if limit is None else min(rows, limit)
    print(f"{'difflib':<{COLUMN}} | histodiff (histogram)")
    print(f"{'-' * COLUMN}-+-{'-' * COLUMN}")
    for i in range(shown):
        lhs = clip(left[i]) if i < len(left) else ""
        rhs = clip(right[i]) if i < len(right) else ""
        print(f"{lhs:<{COLUMN}} | {rhs}")
    if shown < rows:
        more_left, more_right = max(0, len(left) - shown), max(0, len(right) - shown)
        lhs = f"... {more_left} more lines" if more_left else ""
        rhs = f"... {more_right} more lines" if more_right else ""
        print(f"{lhs:<{COLUMN}} | {rhs}")


def scenario(
    number: int, title: str, old: list[str], new: list[str], limit: int | None
) -> tuple[list[histodiff.DiffOp], list[histodiff.DiffOp]]:
    before = difflib_ops(old, new)
    after = histodiff.diff(old, new)

    print("=" * (2 * COLUMN + 3))
    print(f"{number}. {title}  ({len(old)} -> {len(new)} lines)")
    print("=" * (2 * COLUMN + 3))
    side_by_side(render(before), render(after), limit)
    (bh, bc), (ah, ac) = stats(before), stats(after)
    print()
    print(f"{'':16}{'difflib':>10}{'histodiff':>12}")
    print(f"{'hunks':16}{bh:>10}{ah:>12}")
    print(f"{'changed lines':16}{bc:>10}{ac:>12}")
    print()
    return before, after


def change_starts(ops: list[histodiff.DiffOp]) -> list[str]:
    """First line of every changed block."""
    return [(op.b_lines or op.a_lines)[0] for op in ops if op.tag != "equal"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lines", type=int, default=24,
                        help="diff lines to show per scenario (default: 24)")
    parser.add_argument("--full", action="store_true", help="show complete diffs")
    args = parser.parse_args()
    limit = None if args.full else args.lines

    before, after = scenario(
        1, "A function moved to the bottom of a module", *moved_function(), limit
    )
    assert stats(after)[1] * 10 <= stats(before)[1], "histodiff should be ~10x smaller"
    assert change_starts(after) == ["def fetch_orders(client, limit=100):"] * 2

    before, after = scenario(
        2, "One unique row inserted into repeated CSV rows", *unique_row(), limit
    )
    assert stats(after)[1] == 1 < stats(before)[1]

    before, after = scenario(
        3, "A config section moved up (small file, same diff size)",
        *reordered_sections(), limit,
    )
    # Same number of changed lines, but only histodiff's blocks start and end
    # on section boundaries; difflib's cut through the middle of [cache].
    assert stats(after)[1] == stats(before)[1]
    assert change_starts(after) == ["[cache]", "[cache]"]
    assert change_starts(before) != change_starts(after)

    print("All before/after checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
