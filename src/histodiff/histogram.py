"""Histogram diff.

A refinement of patience diff, modelled on Git's ``xhistogram.c`` (the
algorithm behind ``git diff --diff-algorithm=histogram``, originally from
JGit). Instead of requiring anchor lines to be strictly unique, it counts
how often each line occurs in the old region and grows a contiguous run of
matching lines around the *rarest* line it can find. The run is fixed as
matched, and the regions before and after it are diffed the same way.

Selection rule for the run, given a candidate starting at a pair of equal
lines and extended as far as possible in both directions:

1. prefer the run whose rarest line has the lowest occurrence count;
2. among equally rare runs, prefer the longest one.

Lines occurring more than :data:`MAX_CHAIN` times are never used to start a
run (they are too common to be meaningful anchors). If a region has common
lines but all of them are that common, it falls back to Myers.

Differences from Git, deliberately: Git abandons histogram for the *whole*
region as soon as any line exceeds the chain limit, which sends files with
many blank lines straight to Myers; here such lines are simply skipped as
anchors. Git's selection also has a quirk where a longer but more common
run can replace a rarer one; the rule above is applied strictly.
"""

from __future__ import annotations

from collections.abc import Sequence

from ._core import DiffOp, Match, build_ops, intern_lines, trim_common
from .myers import myers_matches

__all__ = ["MAX_CHAIN", "histogram_diff"]

#: Lines occurring more often than this in a region are not used as anchors.
MAX_CHAIN = 64


def _find_run(
    a: Sequence[int],
    alo: int,
    ahi: int,
    b: Sequence[int],
    blo: int,
    bhi: int,
    junk: frozenset[int],
) -> tuple[tuple[int, int, int, int] | None, bool]:
    """Pick the best anchor run in the region.

    Lines in ``junk`` can extend a run but never start one or count towards
    its rarity. Returns ``((a_start, a_end, b_start, b_end) or None,
    has_common)``.
    """
    occurrences: dict[int, list[int]] = {}
    for i in range(alo, ahi):
        occurrences.setdefault(a[i], []).append(i)

    best: tuple[int, int, int, int] | None = None
    best_count = MAX_CHAIN
    best_len = 0
    has_common = False

    j = blo
    while j < bhi:
        next_j = j + 1
        occ = occurrences.get(b[j])
        if occ is not None:
            has_common = True
            count = len(occ)
            if count <= best_count and b[j] not in junk:
                idx = 0
                while idx < count:
                    i = occ[idx]
                    a_start, b_start, a_end, b_end = i, j, i + 1, j + 1
                    rarity = count
                    while (
                        a_start > alo and b_start > blo
                        and a[a_start - 1] == b[b_start - 1]
                    ):
                        a_start -= 1
                        b_start -= 1
                        if rarity > 1 and a[a_start] not in junk:
                            rarity = min(rarity, len(occurrences[a[a_start]]))
                    while a_end < ahi and b_end < bhi and a[a_end] == b[b_end]:
                        if rarity > 1 and a[a_end] not in junk:
                            rarity = min(rarity, len(occurrences[a[a_end]]))
                        a_end += 1
                        b_end += 1

                    # Lines of b inside this run cannot start a better run.
                    next_j = max(next_j, b_end)
                    length = a_end - a_start
                    if rarity < best_count or (
                        rarity == best_count and length > best_len
                    ):
                        best = (a_start, a_end, b_start, b_end)
                        best_count = rarity
                        best_len = length

                    # Skip later occurrences already covered by this run.
                    idx += 1
                    while idx < count and occ[idx] < a_end:
                        idx += 1
        j = next_j

    return best, has_common


def histogram_matches(
    a: Sequence[int],
    alo: int,
    ahi: int,
    b: Sequence[int],
    blo: int,
    bhi: int,
    minimal: bool = False,
    junk: frozenset[int] = frozenset(),
) -> list[Match]:
    """Return (unsorted) matched ``(i, j)`` pairs for two regions.

    ``minimal`` is passed to the Myers fallback. Lines in ``junk`` never
    start an anchor run, though they may extend one or be matched by Myers.
    """
    matches: list[Match] = []
    stack = [(alo, ahi, blo, bhi)]
    while stack:
        alo, ahi, blo, bhi = stack.pop()
        alo, ahi, blo, bhi = trim_common(a, alo, ahi, b, blo, bhi, matches)
        if alo == ahi or blo == bhi:
            continue
        run, has_common = _find_run(a, alo, ahi, b, blo, bhi, junk)
        if run is None:
            if has_common:
                matches.extend(myers_matches(a, alo, ahi, b, blo, bhi, minimal))
            continue
        a_start, a_end, b_start, b_end = run
        matches.extend((a_start + t, b_start + t) for t in range(a_end - a_start))
        stack.append((alo, a_start, blo, b_start))
        stack.append((a_end, ahi, b_end, bhi))
    return matches


def histogram_diff(
    a: Sequence[str], b: Sequence[str], *, minimal: bool = False
) -> list[DiffOp]:
    """Diff two sequences of lines with the histogram algorithm.

    Like patience diff, but anchors on the rarest matching lines rather than
    only strictly unique ones, so it still produces readable output when
    every line repeats somewhere. This is Git's recommended algorithm and
    histodiff's default. ``minimal=True`` disables the cost cap of the
    Myers fallback (see :func:`histodiff.myers_diff`).
    """
    ia, ib = intern_lines(a, b)
    matches = histogram_matches(ia, 0, len(ia), ib, 0, len(ib), minimal)
    matches.sort()
    return build_ops(a, b, matches)
