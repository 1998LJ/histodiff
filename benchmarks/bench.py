#!/usr/bin/env python3
"""Speed and diff size: histodiff vs difflib.

    python benchmarks/bench.py              # full run, plain table
    python benchmarks/bench.py --markdown   # table for the README
    python benchmarks/bench.py --quick      # small inputs, for CI smoke tests

For every scenario each tool aligns the same two line lists; the table shows
the best wall-clock time over ``--repeat`` runs and how many lines the diff
marks as changed (fewer is better, other things equal). difflib is timed
the way ``difflib.unified_diff`` uses it: ``SequenceMatcher(None, a, b)``
with default settings, computing opcodes. histodiff is timed through
``histodiff.diff``, which also includes building the ``DiffOp`` objects.
"""

from __future__ import annotations

import argparse
import difflib
import platform
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

try:
    import histodiff
except ImportError:  # not installed: use the checkout's src/ directory
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import histodiff

Lines = list[str]
Opcodes = list[tuple[str, int, int, int, int]]


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


def python_module(n_funcs: int, seed: int = 0) -> Lines:
    rng = random.Random(seed)
    out: Lines = []
    for i in range(n_funcs):
        out += [
            f"def handler_{i}(request):",
            f'    """Handle request type {i}."""',
            "    if request is None:",
            "        return None",
            f"    value = request.get('field_{rng.randrange(1000)}')",
            "    return value",
            "",
            "",
        ]
    return out


def small_edit(scale: int) -> tuple[Lines, Lines]:
    old = python_module(scale // 8)
    new = list(old)
    new[len(new) // 2] = "    value = request.get('changed')"
    return old, new


def moved_function(scale: int) -> tuple[Lines, Lines]:
    old = python_module(scale // 8)
    new = old[:8] + old[16:] + old[8:16]
    return old, new


def scattered_edits(scale: int) -> tuple[Lines, Lines]:
    rng = random.Random(1)
    old = python_module(scale // 8)
    new = list(old)
    for _ in range(scale // 20):  # roughly one edited line in 20
        new[rng.randrange(len(new))] = f"    # edited {rng.random()}"
    return old, new


def repeated_rows(scale: int) -> tuple[Lines, Lines]:
    old = ["0,0,0,0,0,0,0,0"] * scale
    new = old[: scale // 2] + ["0,0,0,7,0,0,0,0"] + old[scale // 2 :]
    return old, new


def unrelated_files(scale: int) -> tuple[Lines, Lines]:
    """Worst case: two different files sharing only (too common) blank lines."""

    def make(seed: int) -> Lines:
        rng = random.Random(seed)
        return ["" if i % 4 == 3 else f"x = {rng.random()}" for i in range(scale)]

    return make(2), make(3)


SCENARIOS: list[tuple[str, Callable[[int], tuple[Lines, Lines]]]] = [
    ("one line changed", small_edit),
    ("function moved", moved_function),
    ("5% of lines edited", scattered_edits),
    ("row inserted in repeated rows", repeated_rows),
    ("unrelated files (worst case)", unrelated_files),
]


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


def run_difflib(a: Lines, b: Lines) -> Opcodes:
    return difflib.SequenceMatcher(None, a, b).get_opcodes()


def histodiff_tool(algorithm: str, minimal: bool = False) -> Callable[..., Opcodes]:
    def run(a: Lines, b: Lines) -> Opcodes:
        ops = histodiff.diff(a, b, algorithm, minimal=minimal)
        return [op.as_opcode() for op in ops]

    return run


TOOLS: list[tuple[str, Callable[[Lines, Lines], Opcodes]]] = [
    ("difflib", run_difflib),
    ("myers", histodiff_tool("myers")),
    ("patience", histodiff_tool("patience")),
    ("histogram", histodiff_tool("histogram")),
]


def changed(codes: Opcodes) -> int:
    return sum((i2 - i1) + (j2 - j1) for t, i1, i2, j1, j2 in codes if t != "equal")


def measure(
    fn: Callable[[Lines, Lines], Opcodes], a: Lines, b: Lines, repeat: int
) -> tuple[float, int]:
    best = float("inf")
    codes: Opcodes = []
    for _ in range(repeat):
        start = time.perf_counter()
        codes = fn(a, b)
        best = min(best, time.perf_counter() - start)
    return best, changed(codes)


def fmt_time(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms" if seconds >= 0.001 else "<1 ms"
    return f"{seconds:.2f} s"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[2_000, 20_000],
                        help="approximate lines per file (default: 2000 20000)")
    parser.add_argument("--repeat", type=int, default=3,
                        help="runs per measurement; the best is kept (default: 3)")
    parser.add_argument("--quick", action="store_true",
                        help="one small size, one run (CI smoke test)")
    parser.add_argument("--minimal", action="store_true",
                        help="also time histogram with minimal=True")
    parser.add_argument("--markdown", action="store_true", help="markdown table")
    args = parser.parse_args()
    sizes, repeat = ([500], 1) if args.quick else (args.sizes, args.repeat)
    tools = list(TOOLS)
    if args.minimal:
        tools.append(("histogram minimal", histodiff_tool("histogram", True)))

    header = ["scenario", "lines"] + [name for name, _ in tools]
    rows: list[list[str]] = []
    for size in sizes:
        for title, make in SCENARIOS:
            a, b = make(size)
            row = [title, f"{len(a):,}"]
            for _, fn in tools:
                seconds, n_changed = measure(fn, a, b, repeat)
                row.append(f"{fmt_time(seconds)} ({n_changed:,})")
            rows.append(row)
            if not args.markdown:
                print("  ".join(row), file=sys.stderr, flush=True)

    print(f"Python {platform.python_version()} on {platform.machine()}, "
          f"best of {repeat}; cells are time (changed lines)\n")
    if args.markdown:
        print("| " + " | ".join(header) + " |")
        print("|" + "|".join(" --- " for _ in header) + "|")
        for row in rows:
            print("| " + " | ".join(row) + " |")
    else:
        widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
        for row in [header, *rows]:
            print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
