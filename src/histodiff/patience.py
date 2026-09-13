"""Patience diff.

Bram Cohen's patience diff anchors the diff on lines that occur *exactly
once* in both inputs. Such lines (a function signature, a unique comment)
are almost always the "same" line in a meaningful sense, unlike ``}`` or a
blank line. The longest run of unique lines that appear in the same order
in both files becomes the skeleton of the diff; the gaps between anchors
are diffed recursively the same way, and a gap with no unique common lines
falls back to Myers.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence

from ._core import DiffOp, Match, build_ops, intern_lines, trim_common
from .myers import myers_matches

__all__ = ["patience_diff"]


def _unique_common(
    a: Sequence[int], alo: int, ahi: int, b: Sequence[int], blo: int, bhi: int
) -> tuple[list[Match], bool]:
    """Return ``(pairs, has_common)``.

    ``pairs`` holds ``(i, j)`` for every line occurring exactly once in
    ``a[alo:ahi]`` and exactly once in ``b[blo:bhi]``, ordered by ``i``.
    ``has_common`` says whether the regions share any line at all.
    """
    # line -> index of its only occurrence, or -1 once it repeats
    in_a: dict[int, int] = {}
    for i in range(alo, ahi):
        in_a[a[i]] = -1 if a[i] in in_a else i
    in_b: dict[int, int] = {}
    has_common = False
    for j in range(blo, bhi):
        line = b[j]
        if line in in_a:
            has_common = True
            in_b[line] = -1 if line in in_b else j
    pairs = [
        (in_a[line], j) for line, j in in_b.items() if j != -1 and in_a[line] != -1
    ]
    pairs.sort()
    return pairs, has_common


def _longest_increasing(pairs: list[Match]) -> list[Match]:
    """Longest subsequence of ``pairs`` (sorted by ``i``) increasing in ``j``.

    This is the patience-sorting step that gives the algorithm its name:
    O(k log k) for k candidate anchors.
    """
    tails: list[int] = []  # smallest j ending an increasing run of each length
    tail_idx: list[int] = []  # index into pairs for each entry of tails
    prev = [-1] * len(pairs)
    for idx, (_, j) in enumerate(pairs):
        pos = bisect_left(tails, j)
        if pos:
            prev[idx] = tail_idx[pos - 1]
        if pos == len(tails):
            tails.append(j)
            tail_idx.append(idx)
        else:
            tails[pos] = j
            tail_idx[pos] = idx
    result: list[Match] = []
    idx = tail_idx[-1] if tail_idx else -1
    while idx != -1:
        result.append(pairs[idx])
        idx = prev[idx]
    result.reverse()
    return result


def patience_matches(
    a: Sequence[int], alo: int, ahi: int, b: Sequence[int], blo: int, bhi: int
) -> list[Match]:
    """Return (unsorted) matched ``(i, j)`` pairs for two regions."""
    matches: list[Match] = []
    stack = [(alo, ahi, blo, bhi)]
    while stack:
        alo, ahi, blo, bhi = stack.pop()
        alo, ahi, blo, bhi = trim_common(a, alo, ahi, b, blo, bhi, matches)
        if alo == ahi or blo == bhi:
            continue
        pairs, has_common = _unique_common(a, alo, ahi, b, blo, bhi)
        if not pairs:
            if has_common:
                matches.extend(myers_matches(a, alo, ahi, b, blo, bhi))
            continue
        i, j = alo, blo
        for ai, bj in _longest_increasing(pairs):
            matches.append((ai, bj))
            stack.append((i, ai, j, bj))
            i, j = ai + 1, bj + 1
        stack.append((i, ahi, j, bhi))
    return matches


def patience_diff(a: Sequence[str], b: Sequence[str]) -> list[DiffOp]:
    """Diff two sequences of lines with the patience algorithm.

    Lines unique to both sides are used as fixed anchors, which keeps moved
    or rewritten blocks together instead of matching incidental lines like
    ``}`` or blank lines. Gaps without unique lines are diffed with Myers.
    """
    ia, ib = intern_lines(a, b)
    matches = patience_matches(ia, 0, len(ia), ib, 0, len(ib))
    matches.sort()
    return build_ops(a, b, matches)
